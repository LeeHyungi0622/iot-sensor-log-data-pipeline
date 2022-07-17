import time
import datetime
import json
from sense_hat import SenseHat
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

sense = SenseHat()

topic = "sensor/data"
client_id = "raspberrypi"

# Callback when connection is accidentally lost.

def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))

# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(
        return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
    resubscribe_results = resubscribe_future.result()
    print("Resubscribe results: {}".format(resubscribe_results))

    for topic, qos in resubscribe_results['topics']:
        if qos is None:
            sys.exit("Server rejected resubscribe to topic: {}".format(topic))


# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))


def collect_and_send_data():
    publish_count = 0
    while(True):

        humidity = sense.get_humidity()
        print("Humidity: %s %%rH" % humidity)

        temp = sense.get_temperature()
        print("Temperature: %s C" % temp)

        pressure = sense.get_pressure()
        print("Pressure: %s Millibars" % pressure)

        orientation = sense.get_orientation_degrees()
        print("p: {pitch}, r: {roll}, y: {yaw}".format(**orientation))

        timestamp = datetime.datetime.fromtimestamp(
            time.time()).strftime('%Y-%m-%d %H:%M:%S')

        message = {
            "client_id": client_id,
            "timestamp": timestamp,
            "humidity": humidity,
            "temperature": temp,
            "pressure": pressure,
            "pitch": orientation['pitch'],
            "roll": orientation['roll'],
            "yaw": orientation['yaw'],
            "count": publish_count
        }
        print("Publishing message to topic '{}': {}".format(topic, message))

        mqtt_connection.publish(
            topic=topic,
            payload=json.dumps(message),
            qos=mqtt.QoS.AT_LEAST_ONCE)
        time.sleep(1)
        publish_count += 1


if __name__ == '__main__':
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint="a2tageu4ijt418-ats.iot.ap-northeast-2.amazonaws.com",
        cert_filepath="certificates/raspberrypi-sensor-device.cert.pem",
        pri_key_filepath="certificates/raspberrypi-sensor-device.private.key",
        client_bootstrap=client_bootstrap,
        ca_filepath="certificates/root-CA.crt",
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=client_id,
        clean_session=False,
        keep_alive_secs=6)

    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    # Subscribe
    print("Subscribing to topic '{}'...".format(topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    collect_and_send_data()