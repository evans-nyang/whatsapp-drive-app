import hashlib
import hmac


def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """
    Verifies the X-Hub-Signature-256 header WhatsApp sends with every webhook
    POST. Uses hmac.compare_digest to avoid timing-attack leakage.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)
