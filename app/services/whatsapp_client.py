import httpx
from loguru import logger

from app.config import get_settings

settings = get_settings()


class WhatsAppClient:
    """
    Thin wrapper around the WhatsApp Cloud (Graph) API. Used by:
      - media worker: to resolve a media_id to a download URL and fetch bytes
      - notification worker: to send confirmation/failure messages back to users

    Media URLs returned by the Graph API expire within minutes, so callers
    should download promptly after resolving the URL rather than caching it.
    """

    def __init__(self) -> None:
        self._base_url = settings.whatsapp_graph_base_url
        self._headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}

    async def get_media_url(self, media_id: str) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{self._base_url}/{media_id}", headers=self._headers)
            resp.raise_for_status()
            return resp.json()["url"]

    async def download_media(self, media_url: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(media_url, headers=self._headers)
            resp.raise_for_status()
            return resp.content

    async def send_text_message(self, to_phone: str, body: str) -> None:
        url = f"{self._base_url}/{settings.whatsapp_phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": body},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            if resp.status_code >= 400:
                logger.error(f"failed to send WhatsApp message: {resp.status_code} {resp.text}")
            resp.raise_for_status()
