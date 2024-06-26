import pika
import json
import time
from enum import Enum

class RabbitMQConsumer:
    @staticmethod
    def process(message: dict, functions: dict):
        functions.update(globals())
        if 'function' not in message.keys():
            # Invalid request, do not retry
            return RequestStatusEnum.FAIL
        return functions[message['function']](*message['args'])

    @staticmethod
    def send_status(queue: str, message: dict, status_channel: pika.adapters.blocking_connection.BlockingChannel):
        # Establish a connection and channel for sending status messages
        status_channel.queue_declare(queue=queue, durable=True)

        # Publish the status message
        status_channel.basic_publish(
            exchange='',
            routing_key=queue,
            body=json.dumps(message).encode(),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent message
                correlation_id=message['correlation_id']
            )
        )

    def consume_queue(self, queue: str, functions: dict):
        while True:
            try:
                conn = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
            except pika.exceptions.AMQPConnectionError:
                print(f"Retrying connection for queue {queue}...")
                time.sleep(5)
            except Exception as e:
                print(f"Failed to connect to RabbitMQ: {str(e)}")
                time.sleep(5)
            else:
                print(f"RabbitMQ Connected")
                break
        channel = conn.channel()
        channel.queue_declare(queue=queue, durable=True)
        while True:
            try:
                for method, properties, body in channel.consume(queue=queue, inactivity_timeout=30):
                    if body:
                        res = json.loads(body.decode())
                        response = self.process(res, functions)

                        # Prepare the status message
                        status_message = {
                            'status': 'Processed',
                            'correlation_id': properties.correlation_id
                        }

                        # We signal that the message is received and processed, rabbitMQ will now remove it from the
                        # queue or retry
                        if response == RequestStatusEnum.SUCCESS:
                            channel.basic_ack(delivery_tag=method.delivery_tag)
                        elif response == RequestStatusEnum.FAIL:
                            status_message['status'] = 'Failed'
                            channel.basic_ack(delivery_tag=method.delivery_tag)
                        else:
                            # Try again later
                            status_message['status'] = 'Retrying'
                            channel.basic_nack(delivery_tag=method.delivery_tag)
                        # Send the status message to the status queue
                        self.send_status(properties.reply_to, status_message, channel)
            except (pika.exceptions.StreamLostError, pika.exceptions.ConnectionClosedByBroker):
                print("Connection to RabbitMQ Lost. Retrying connection...")
                try:
                    conn.close()
                except pika.exceptions.ConnectionWrongStateError:
                    pass
                while True:
                    try:
                        conn = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
                    except pika.exceptions.AMQPConnectionError:
                        print(f"Retrying connection for queue {queue}...")
                        time.sleep(5)
                    except Exception as e:
                        print(f"Failed to connect to RabbitMQ: {str(e)}")
                        time.sleep(5)
                    else:
                        print(f"RabbitMQ Connected")
                        break
                    time.sleep(3)
                channel = conn.channel()
                channel.queue_declare(queue=queue, durable=True)
                continue

class RequestStatusEnum(Enum):
    SUCCESS = 1
    RETRY = 2
    FAIL = 3