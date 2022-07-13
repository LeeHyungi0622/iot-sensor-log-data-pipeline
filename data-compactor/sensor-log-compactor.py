"""
본 코드는 AWS Lambda의 Code source에 작성합니다.
"""
import boto3
from datetime import datetime
import logging
# lambda 함수에서 환경변수 값을 가져오기 위해 import
import os
#log 찍을때 stderror
import sys

# DynamoDB Client 생성하기
dynamodb_client = boto3.client('dynamodb')
dynamodb_resource = boto3.resource('dynamodb')
table = dynamodb_resource.Table('sensor_counter')

# CTAS QUERY 구성을 위한 환경변수 선언
SOURCE_DATABASE = os.getenv('SOURCE_DATABASE')
SOURCE_TABLE_NAME = os.getenv('SOURCE_TABLE_NAME')
NEW_DATABASE = os.getenv('NEW_DATABASE')
NEW_TABLE_NAME = os.getenv('NEW_TABLE_NAME')
BUCKET_NAME = os.getenv('BUCKET_NAME')
COLUMN_NAMES = os.getenv('COLUMN_NAMES', '*')
WORK_GROUP = os.getenv('WORK_GROUP', 'primary')

# CTAS QUERY 정의
CTAS_QUERY_FMT = '''CREATE TABLE {new_database}.tmp_{new_table_name}
WITH (
  external_location='{location}',
  format = 'JSON',
  bucketed_by=ARRAY['time'],
  bucket_count=1)
AS SELECT {columns}
FROM {source_database}.{source_table_name}
WITH DATA
'''

def increase_counter():
    try:
      table.update_item(
        Key={
          "ID": "Counter"
        },
        UpdateExpression='SET #prev = #prev + :increase',
        ExpressionAttributeNames={
            "#prev":"TotalCount"
        },
        ExpressionAttributeValues={
            ':increase': 1
        }
      )
    except Exception as e:
      logging.error("type: %s", type(e))
      logging.error(e)

def check_count_num():
    # 누적된 파일의 갯수를 확인해서 총 count 수가 20이 되면, 20개의 파일을 압축해서 compation을 진행하도록 처리한다.
    try:
        itemdata = table.get_item(
            Key={
                "ID": "Counter"
            },
            ConsistentRead=True
        )
        total_count = itemdata['Item']['TotalCount']
        print('type:', type(total_count), 'value:', total_count)
        return total_count > 5
    except Exception as e:
        logging.error("type : %s", type(e))
        logging.error(e)

# CTAS QUERY에서의 parameter를 받아서 처리
def run_ctas(athena_client, now_timestamp):
    year, month, day, hour, minute = (now_timestamp.year, now_timestamp.month, now_timestamp.day, now_timestamp.hour, now_timestamp.minute)

    new_table_name = '{table}_{year}{month:02}{day:02}{hour:02}{minute:02}'.format(table=NEW_TABLE_NAME,year=year,month=month,day=day,hour=hour,minute=minute)

    output_location = 's3://{bucket_name}/tmp'.format(bucket_name=BUCKET_NAME)
    # compacted log 파일은 지정 bucket의 하위 compacted_log 폴더 아래에 저장
    external_location = 's3://{bucket_name}/{dir}'.format(bucket_name=BUCKET_NAME, dir=new_table_name)
    
    query = CTAS_QUERY_FMT.format(new_database=NEW_DATABASE, new_table_name=new_table_name,
                                  source_database=SOURCE_DATABASE, source_table_name=SOURCE_TABLE_NAME, columns=COLUMN_NAMES,
                                  location=external_location)

    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={
            'Database': NEW_DATABASE
        },
        ResultConfiguration={
            'OutputLocation': output_location
        },
        WorkGroup=WORK_GROUP
    )
    
    print('[LOG] QueryString:\n{}'.format(query), file=sys.stderr)
    print('[LOG] ExternalLocation: {}'.format(external_location), file=sys.stderr)
    print('[LOG] OutputLocation: {}'.format(output_location), file=sys.stderr)
    print('[LOG] the response of CTAS query : ', response)
    print('[LOG] QueryExecutionId: {}'.format(response['QueryExecutionId']), file=sys.stderr)

    return new_table_name

# 압축시에 생성되는 tmp 파일 삭제하는 메소드
def drop_tmp_table(athena_client):
    output_location = 's3://{bucket_name}/tmp'.format(bucket_name=BUCKET_NAME)
    # Athena에 생성된 tmp table 삭제
    query = 'DROP TABLE IF EXISTS {database}.tmp_{table}_*'.format(database=NEW_DATABASE, table=NEW_TABLE_NAME)

    print('[LOG] QueryString:\n{}'.format(query), file=sys.stderr)
    print('[LOG] OutputLocation: {}'.format(output_location), file=sys.stderr)

    response = athena_client.start_query_execution(
        QueryString=query,
        ResultConfiguration={
            'OutputLocation': output_location
        },
        WorkGroup=WORK_GROUP
    )
    print('[LOG] the response of DROP TABLE IF EXISTS query : ', response)
    print('[LOG] QueryExecutionId: {}'.format(response['QueryExecutionId']), file=sys.stderr)

def empty_s3_log_folder():
    s3_client = boto3.client("s3")

    response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix="generated_log/")
    files_in_folder = response["Contents"]
    files_to_delete = []
    # Create Key Array to pass to delete_objects function
    for f in files_in_folder:
        files_to_delete.append({"Key": f["Key"]})

    # Delete all files in a folder
    response = s3_client.delete_objects(
        Bucket=BUCKET_NAME, Delete={"Objects": files_to_delete}
    )
    print(response)

# DynamoDB TABLE의 COUNT 값 초기화
def initialize_dynamo_db_tbl():
    try:
      table.update_item(
        Key={
          "ID": "Counter"
        },
        UpdateExpression='SET #prev = #prev - #prev',
        ExpressionAttributeNames={
            "#prev":"TotalCount"
        }
      )
    except Exception as e:
      logging.error("type: %s", type(e))
      logging.error(e)

def lambda_handler(event, context):
    client = boto3.client('athena')
    now_timestamp = datetime.now()
    # print(table.scan())
    # 만약에 DynamoDB에 count된 값이 5보다 큰 경우,
    if check_count_num():
        # 테이블을 압축하고, 자동생성되는 tmp 파일을 제거
        run_ctas(client, now_timestamp)
        # drop_tmp_table(client)
        # 로그 데이터가 쌓인 디렉토리를 비우기
        empty_s3_log_folder()
        # DynamoDB의 TotalCount값을 0으로 초기화
        initialize_dynamo_db_tbl()

    # 아직 DynamoDB에 count된 값이 5보다 작은 경우,
    else:
        increase_counter()