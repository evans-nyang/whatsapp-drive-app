import hashlib
import hmac

from app.webhook.security import verify_signature

APP_SECRET = "test_secret"


def _sign(body: bytes) -> str:
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_signature_accepts_valid_signature():
    body = b'{"hello": "world"}'
    signature = _sign(body)
    assert verify_signature(body, signature, APP_SECRET) is True


def test_verify_signature_rejects_tampered_body():
    body = b'{"hello": "world"}'
    signature = _sign(body)
    tampered_body = b'{"hello": "mallory"}'
    assert verify_signature(tampered_body, signature, APP_SECRET) is False


def test_verify_signature_rejects_missing_header():
    body = b'{"hello": "world"}'
    assert verify_signature(body, None, APP_SECRET) is False


def test_verify_signature_rejects_wrong_prefix():
    body = b'{"hello": "world"}'
    assert verify_signature(body, "sha1=deadbeef", APP_SECRET) is False
