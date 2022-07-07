"""
본 코드는 AWS Lambda의 Code source에 작성합니다.
"""
import boto3
import logging

# DynamoDB Client 생성하기
dynamodb_client = boto3.client('dynamodb')
dynamodb_resource = boto3.resource('dynamodb')
table = dynamodb_resource.Table('sensor_counter')

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


def lambda_handler(event, context):
    # print(table.scan())
    
    # try:
    #     itemdata = table.get_item(
    #         Key={
    #             "ID": "Counter"
    #         },
    #         ConsistentRead=True
    #     )
    #     print(itemdata['Item'])
    # except Exception as e:
    #     logging.error("type : %s", type(e))
    #     logging.error(e)
    increase_counter()