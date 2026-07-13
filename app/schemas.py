from typing import Literal

from pydantic import BaseModel


class MediaReceivedEvent(BaseModel):
    """Published by the webhook service when a new image message arrives."""

    message_id: str
    media_id: str
    mime_type: str | None = None
    sender_phone: str
    timestamp: str | None = None
    whatsapp_phone_number_id: str | None = None


class MediaUploadedEvent(BaseModel):
    """Published by the media worker once the image is safely in Drive."""

    message_id: str
    sender_phone: str
    drive_file_id: str
    drive_file_url: str


class MediaFailedEvent(BaseModel):
    """Published by the media worker if download or upload fails permanently."""

    message_id: str
    sender_phone: str
    reason: str


RoutingKey = Literal["media.received", "media.uploaded", "media.failed"]
