"""
Notification worker.

Consumes `media.uploaded` and `media.failed` events and sends the
corresponding confirmation/error message back to the user via WhatsApp.

This is the only service that sends outbound WhatsApp messages. Keeping it
separate from the media worker means a WhatsApp API outage or rate limit
never blocks image storage — uploads keep succeeding and events simply queue
up until this worker can catch up.

Run with:
    python -m app.workers.notification_worker
"""

import asyncio

from loguru import logger

from app.config import get_settings
from app.logging_config import configure_logging
from app.messaging.rabbitmq import bind_queue, consume, get_connection, get_exchange
from app.schemas import MediaFailedEvent, MediaUploadedEvent
from app.services.whatsapp_client import WhatsAppClient

settings = get_settings()
configure_logging("notification-worker")

whatsapp_client = WhatsAppClient()


async def handle_uploaded(payload: dict) -> None:
    event = MediaUploadedEvent(**payload)
    logger.info(f"notifying success for message {event.message_id}")
    await whatsapp_client.send_text_message(
        to_phone=event.sender_phone,
        body="Got it! Your photo has been saved to Drive. \u2705",
    )


async def handle_failed(payload: dict) -> None:
    event = MediaFailedEvent(**payload)
    logger.info(f"notifying failure for message {event.message_id}")
    await whatsapp_client.send_text_message(to_phone=event.sender_phone, body=event.reason)


async def main() -> None:
    connection = await get_connection()
    channel = await connection.channel()
    exchange = await get_exchange(channel)
    queue = await bind_queue(
        channel, exchange, "notification-queue", ["media.uploaded", "media.failed"]
    )

    logger.info("notification worker started, waiting for messages")

    async def handler(payload: dict) -> None:
        # Route on which fields are present rather than a separate topic
        # per handler — routing_key already filtered us to the right queue,
        # this just disambiguates the two event shapes within it.
        if "drive_file_id" in payload:
            await handle_uploaded(payload)
        else:
            await handle_failed(payload)

    await consume(queue, handler, prefetch_count=20)


if __name__ == "__main__":
    asyncio.run(main())
