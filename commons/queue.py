import json
import logging
import pika
from commons.config import settings

logger = logging.getLogger(__name__)

def get_rabbitmq_connection():
    """
    Establishes and returns a connection to RabbitMQ.
    """
    credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=60
    )
    return pika.BlockingConnection(parameters)

def publish_message(queue_name: str, payload: dict):
    """
    Publishes a JSON payload to a specified RabbitMQ queue.
    Creates a temporary connection to perform the write and closes it.
    """
    connection = None
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        # Ensure queue exists (durable for message safety)
        channel.queue_declare(queue=queue_name, durable=True)
        
        message_body = json.dumps(payload)
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=message_body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent on disk
                content_type="application/json"
            )
        )
        logger.info(f"Queue: Published message to '{queue_name}'")
    except Exception as e:
        logger.error(f"Queue Error: Failed to publish message to '{queue_name}': {e}")
        raise e
    finally:
        if connection and not connection.is_closed:
            connection.close()
