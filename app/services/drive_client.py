import asyncio
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.config import get_settings

settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveClient:
    """
    Wraps the Google Drive API v3 using a service account.

    Note: googleapiclient is synchronous. We run its calls in a thread pool
    via asyncio.to_thread so the worker's event loop is never blocked — this
    is what keeps the media worker able to process other messages concurrently
    while an upload is in flight.

    Auth model: this uses a single service account owning all uploads, with
    one subfolder per WhatsApp phone number under GOOGLE_DRIVE_ROOT_FOLDER_ID.
    If you instead want images to land in each *user's own* personal Drive,
    swap this for per-user OAuth2 credentials (refresh tokens stored encrypted
    in Postgres) and pass those into `build()` instead of the service account.
    """

    def __init__(self) -> None:
        credentials = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json, scopes=SCOPES
        )
        self._service = build("drive", "v3", credentials=credentials)

    def _find_or_create_folder_sync(self, phone_number: str) -> str:
        query = (
            f"'{settings.google_drive_root_folder_id}' in parents "
            f"and name = '{phone_number}' "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        )
        results = self._service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        folder_metadata = {
            "name": phone_number,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [settings.google_drive_root_folder_id],
        }
        folder = self._service.files().create(body=folder_metadata, fields="id").execute()
        return folder["id"]

    async def find_or_create_user_folder(self, phone_number: str) -> str:
        return await asyncio.to_thread(self._find_or_create_folder_sync, phone_number)

    def _upload_sync(self, filename: str, content: bytes, mime_type: str, folder_id: str) -> dict:
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=True)
        file_metadata = {"name": filename, "parents": [folder_id]}
        return (
            self._service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )

    async def upload_image(
        self, filename: str, content: bytes, mime_type: str, folder_id: str
    ) -> tuple[str, str]:
        """Returns (drive_file_id, web_view_link)."""
        result = await asyncio.to_thread(self._upload_sync, filename, content, mime_type, folder_id)
        return result["id"], result["webViewLink"]
