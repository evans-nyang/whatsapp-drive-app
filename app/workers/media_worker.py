"""
Media processing worker.

Consumes `media.received` events. For each one:
  1. Resolves the WhatsApp media_id to a download URL and fetches the bytes
  2. Finds/creates the sender's Drive folder and uploads the image
  3. Upserts a MediaEvent row in Postgres with the outcome
  4. Publishes `media.uploaded` or `media.failed` for the notification worker

This is the only service that talks to Google Drive. It is fully stateless —
horizontally scale by running more replicas; RabbitMQ's prefetch/ack model
distributes work across them automatically.

Run with:
    python -m app.workers.media_worker
"""

import asyncio
import mimetypes
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select

from app.config import get_settings
from app.db.models import MediaEvent, MediaStatus, User
from app.db.session import get_session
from app.logging_config import configure_logging
from app.messaging.rabbitmq import bind_queue, consume, get_connection, get_exchange, publish_event
from app.schemas import MediaFailedEvent, MediaReceivedEvent, MediaUploadedEvent
from app.services.drive_client import DriveClient
from app.services.whatsapp_client import WhatsAppClient

settings = get_settings()
configure_logging("media-worker")

whatsapp_client = WhatsAppClient()
drive_client = DriveClient()


async def _get_or_create_user(session, phone_number: str) -> User:
    result = await session.execute(select(User).where(User.whatsapp_phone_number == phone_number))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(whatsapp_phone_number=phone_number)
    session.add(user)
    await session.flush()  # get user.id without committing yet
    return user


async def handle_media_received(payload: dict, exchange) -> None:
    event = MediaReceivedEvent(**payload)
    logger.info(f"processing media.received for message {event.message_id}")

    async with get_session() as session:
        media_event = MediaEvent(
            whatsapp_message_id=event.message_id,
            sender_phone=event.sender_phone,
            media_id=event.media_id,
            mime_type=event.mime_type,
            status=MediaStatus.PENDING,
        )
        session.add(media_event)

        try:
            media_url = await whatsapp_client.get_media_url(event.media_id)
            content = await whatsapp_client.download_media(media_url)
            media_event.status = MediaStatus.DOWNLOADED

            user = await _get_or_create_user(session, event.sender_phone)
            media_event.user_id = user.id

            if not user.drive_folder_id:
                user.drive_folder_id = await drive_client.find_or_create_user_folder(
                    event.sender_phone
                )

            extension = mimetypes.guess_extension(event.mime_type or "image/jpeg") or ".jpg"
            filename = f"{event.message_id}_{datetime.now(UTC):%Y%m%dT%H%M%S}{extension}"

            drive_file_id, drive_url = await drive_client.upload_image(
                filename=filename,
                content=content,
                mime_type=event.mime_type or "image/jpeg",
                folder_id=user.drive_folder_id,
            )

            media_event.status = MediaStatus.UPLOADED
            media_event.drive_file_id = drive_file_id

            await publish_event(
                exchange,
                "media.uploaded",
                MediaUploadedEvent(
                    message_id=event.message_id,
                    sender_phone=event.sender_phone,
                    drive_file_id=drive_file_id,
                    drive_file_url=drive_url,
                ).model_dump(),
            )

        except Exception as exc:
            logger.exception(f"failed to process message {event.message_id}")
            media_event.status = MediaStatus.FAILED
            media_event.error_message = str(exc)

            await publish_event(
                exchange,
                "media.failed",
                MediaFailedEvent(
                    message_id=event.message_id,
                    sender_phone=event.sender_phone,
                    reason="We couldn't save your image right now. Please try sending it again.",
                ).model_dump(),
            )


async def main() -> None:
    connection = await get_connection()
    channel = await connection.channel(publisher_confirms=True)
    exchange = await get_exchange(channel)
    queue = await bind_queue(channel, exchange, "media-processing-queue", ["media.received"])

    logger.info("media worker started, waiting for messages")

    async def handler(payload: dict) -> None:
        await handle_media_received(payload, exchange)

    await consume(queue, handler, prefetch_count=10)


if __name__ == "__main__":
    asyncio.run(main())
