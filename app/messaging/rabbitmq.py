import json
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage, AbstractRobustConnection
from loguru import logger

from app.config import get_settings

settings = get_settings()


async def get_connection() -> AbstractRobustConnection:
    return await aio_pika.connect_robust(settings.rabbitmq_url)


async def get_exchange(channel: aio_pika.Channel) -> AbstractExchange:
    return await channel.declare_exchange(
        settings.media_events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
    )


async def publish_event(exchange: AbstractExchange, routing_key: str, payload: dict) -> None:
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=routing_key,
    )
    logger.info(f"published event routing_key={routing_key}")


async def bind_queue(
    channel: aio_pika.Channel,
    exchange: AbstractExchange,
    queue_name: str,
    routing_keys: list[str],
) -> aio_pika.Queue:
    """
    Declares a durable queue with a dead-letter exchange, and binds it to the
    given routing keys. Messages that are nacked repeatedly (or expire) land
    in `<queue_name>.dlq` for manual inspection instead of being lost.
    """
    dlx_name = f"{queue_name}.dlx"
    dlq_name = f"{queue_name}.dlq"

    dlx = await channel.declare_exchange(dlx_name, aio_pika.ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(dlq_name, durable=True)
    await dlq.bind(dlx)

    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={"x-dead-letter-exchange": dlx_name},
    )
    for key in routing_keys:
        await queue.bind(exchange, routing_key=key)

    return queue


async def consume(
    queue: aio_pika.Queue,
    handler: Callable[[dict], Awaitable[None]],
    prefetch_count: int = 10,
) -> None:
    """
    Runs forever, calling `handler(payload)` for each message. Acks on
    success; on exception, nacks WITHOUT requeue so the message is routed
    to the dead-letter queue instead of retried forever in a hot loop.
    Transient errors should be retried inside the handler itself.
    """
    await queue.channel.set_qos(prefetch_count=prefetch_count)

    async with queue.iterator() as queue_iter:
        message: AbstractIncomingMessage
        async for message in queue_iter:
            try:
                payload = json.loads(message.body)
                await handler(payload)
                await message.ack()
            except Exception:
                logger.exception("event handler failed, sending to DLQ")
                await message.nack(requeue=False)
