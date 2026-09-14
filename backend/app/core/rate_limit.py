import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'timestamp')
local tokens = tonumber(data[1])
local timestamp = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  timestamp = now
end
tokens = math.min(capacity, tokens + math.max(0, now - timestamp) * refill)
local allowed = 0
local retry_after_ms = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
else
  retry_after_ms = math.ceil(((requested - tokens) / refill) * 1000)
end
redis.call('HMSET', key, 'tokens', tokens, 'timestamp', now)
redis.call('EXPIRE', key, math.ceil(capacity / refill) * 2)
return {allowed, retry_after_ms}
"""


class RedisScript(Protocol):
    async def __call__(
        self,
        keys: list[str],
        args: list[str],
    ) -> object: ...


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class TokenBucketRateLimiter:
    def __init__(
        self,
        redis: Redis | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._redis = redis
        self._settings = settings or get_settings()

    async def check(self, identifier: str) -> RateLimitDecision:
        if not self._settings.rate_limit_enabled:
            return RateLimitDecision(allowed=True)
        try:
            result = await self._eval(
                [f"rate:{identifier}"],
                [
                    str(self._settings.rate_limit_capacity),
                    str(self._settings.rate_limit_refill_per_second),
                    str(time.time()),
                    "1",
                ],
            )
        except (RedisError, OSError):
            logger.warning("rate_limit_redis_unavailable", exc_info=True)
            return RateLimitDecision(allowed=True)

        if not isinstance(result, (list, tuple)) or len(result) < 2:
            return RateLimitDecision(allowed=True)
        allowed = int(result[0]) == 1
        retry_after_ms = max(0, int(result[1]))
        return RateLimitDecision(
            allowed=allowed,
            retry_after_seconds=(retry_after_ms + 999) // 1000,
        )

    async def _eval(
        self,
        keys: list[str],
        args: list[str],
    ) -> object:
        client = self._redis or get_redis()
        result = cast(
            Awaitable[object],
            client.eval(_TOKEN_BUCKET_SCRIPT, len(keys), *keys, *args),
        )
        return await result
