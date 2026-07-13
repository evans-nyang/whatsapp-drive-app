import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """
    Lazily creates a single Redis connection pool per process. redis-py's
    async client is safe to share across coroutines/requests.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def is_duplicate_message(message_id: str, ttl_seconds: int = 60 * 60 * 24) -> bool:
    """
    Atomically marks a WhatsApp message_id as seen. Returns True if it was
    ALREADY seen (i.e. this is a duplicate delivery that should be skipped).
    """
    client = get_redis()
    was_new = await client.set(f"whatsapp:msg:{message_id}", "1", nx=True, ex=ttl_seconds)
    return not was_new
