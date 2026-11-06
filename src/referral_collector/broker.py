"""RabbitMQ connectivity for the collector."""

import pika
from pydantic import AmqpDsn


def _connect(rabbitmq_url: AmqpDsn) -> pika.BlockingConnection:
    parameters = pika.URLParameters(str(rabbitmq_url))
    parameters.connection_attempts = 1
    parameters.socket_timeout = 3
    parameters.stack_timeout = 5
    parameters.blocked_connection_timeout = 5
    return pika.BlockingConnection(parameters)


def check_broker(rabbitmq_url: AmqpDsn) -> None:
    """Raise if RabbitMQ cannot open an AMQP channel."""
    with _connect(rabbitmq_url) as connection:
        connection.channel().close()


def smoke_broker(rabbitmq_url: AmqpDsn) -> None:
    """Publish, retrieve, and acknowledge one disposable message."""
    payload = b"referral-collector smoke"
    with _connect(rabbitmq_url) as connection:
        channel = connection.channel()
        queue = channel.queue_declare(queue="", exclusive=True).method.queue
        channel.confirm_delivery()
        channel.basic_publish(exchange="", routing_key=queue, body=payload, mandatory=True)
        delivery, _, body = channel.basic_get(queue=queue, auto_ack=False)
        if delivery is None or body != payload:
            raise RuntimeError("Unexpected RabbitMQ smoke test delivery")
        channel.basic_ack(delivery_tag=delivery.delivery_tag)
