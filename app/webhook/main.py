"""
FastAPI webhook service.

Responsible ONLY for:
  1. Verifying WhatsApp webhook signatures
  2. Handling Meta's GET verification handshake
  3. Deduping redelivered events via Redis
  4. Publishing a `media.received` event to RabbitMQ
  5. Returning 200 fast

Run with:
    uvicorn app.webhook.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from contextlib import asynccontextmanager
from typing import Any

import aio_pika
from fastapi import FastAPI, Header, HTTPException, Request, Response
from loguru import logger

from app.cache.redis_client import is_duplicate_message
from app.config import get_settings
from app.logging_config import configure_logging
from app.messaging.rabbitmq import get_connection, get_exchange, publish_event
from app.schemas import MediaReceivedEvent
from app.webhook.security import verify_signature

settings = get_settings()
configure_logging("webhook-service")


class AppState:
    rabbit_connection: aio_pika.RobustConnection
    rabbit_channel: aio_pika.Channel
    exchange: aio_pika.Exchange


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.rabbit_connection = await get_connection()
    state.rabbit_channel = await state.rabbit_connection.channel(publisher_confirms=True)
    state.exchange = await get_exchange(state.rabbit_channel)
    logger.info("webhook service started")
    yield
    await state.rabbit_connection.close()
    logger.info("webhook service shut down cleanly")


app = FastAPI(title="whatsapp-webhook-service", lifespan=lifespan)


@app.get("/webhook")
async def verify_webhook(request: Request):
    # Meta sends these as query params on the verification handshake.
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        logger.info("webhook verification succeeded")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("webhook verification failed: bad token or mode")
    raise HTTPException(status_code=403, detail="verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    raw_body = await request.body()

    if not verify_signature(raw_body, x_hub_signature_256, settings.whatsapp_app_secret):
        logger.warning("rejected webhook: invalid signature")
        raise HTTPException(status_code=401, detail="invalid signature")

    payload = await request.json()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                await _handle_message(message, value)

    # Always 200 quickly — WhatsApp only needs to know delivery succeeded.
    return {"status": "received"}


async def _handle_message(message: dict[str, Any], value: dict[str, Any]) -> None:
    message_id = message.get("id")
    message_type = message.get("type")

    if message_type != "image":
        logger.debug(f"ignoring non-image message {message_id} ({message_type})")
        return

    if await is_duplicate_message(message_id):
        logger.info(f"duplicate message {message_id}, skipping publish")
        return

    event = MediaReceivedEvent(
        message_id=message_id,
        media_id=message["image"]["id"],
        mime_type=message["image"].get("mime_type"),
        sender_phone=message.get("from"),
        timestamp=message.get("timestamp"),
        whatsapp_phone_number_id=value.get("metadata", {}).get("phone_number_id"),
    )

    await publish_event(state.exchange, "media.received", event.model_dump())
    logger.info(f"published media.received for message {message_id}")


@app.get("/healthz")
async def healthz():
    try:
        if state.rabbit_connection.is_closed:
            raise RuntimeError("rabbitmq connection closed")
        return {"status": "ok"}
    except Exception as exc:
        logger.error(f"health check failed: {exc}")
        raise HTTPException(status_code=503, detail="unhealthy") from exc
