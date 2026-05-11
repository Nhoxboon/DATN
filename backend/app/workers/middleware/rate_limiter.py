"""Rate limiter implementation using token bucket algorithm."""

import time
from typing import Optional
import redis
from app.core.config import get_settings

settings = get_settings()


class TokenBucketRateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(
        self,
        key: str,
        max_tokens: int,
        refill_rate: float,
        refill_interval: float = 1.0
    ):
        """
        Initialize rate limiter.

        Args:
            key: Unique key for this rate limiter
            max_tokens: Maximum tokens in bucket
            refill_rate: Tokens to add per refill interval
            refill_interval: Interval in seconds between refills
        """
        self.key = f"rate_limit:{key}"
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.refill_interval = refill_interval
        redis_url = settings.redis_url
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

    def _get_bucket_state(self) -> tuple[float, float]:
        """Get current bucket state."""
        pipe = self.redis_client.pipeline()
        pipe.get(f"{self.key}:tokens")
        pipe.get(f"{self.key}:last_refill")
        results = pipe.execute()

        tokens = float(results[0]) if results[0] else self.max_tokens
        last_refill = float(results[1]) if results[1] else time.time()

        return tokens, last_refill

    def _set_bucket_state(self, tokens: float, last_refill: float):
        """Set bucket state."""
        pipe = self.redis_client.pipeline()
        pipe.set(f"{self.key}:tokens", str(tokens))
        pipe.set(f"{self.key}:last_refill", str(last_refill))
        pipe.expire(f"{self.key}:tokens", int(self.refill_interval * 10))
        pipe.expire(f"{self.key}:last_refill", int(self.refill_interval * 10))
        pipe.execute()

    def acquire(self, tokens: int = 1, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Try to acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire
            blocking: Wait if not enough tokens
            timeout: Max seconds to wait

        Returns:
            True if tokens acquired, False otherwise
        """
        start_time = time.time()

        while True:
            current_tokens, last_refill = self._get_bucket_state()
            now = time.time()

            # Calculate refill
            time_passed = now - last_refill
            refills = time_passed / self.refill_interval
            tokens_to_add = refills * self.refill_rate

            # Update tokens
            new_tokens = min(self.max_tokens, current_tokens + tokens_to_add)

            # Check if we have enough tokens
            if new_tokens >= tokens:
                self._set_bucket_state(new_tokens - tokens, now)
                return True

            if not blocking:
                return False

            if timeout and (time.time() - start_time) >= timeout:
                return False

            # Calculate wait time
            tokens_needed = tokens - new_tokens
            wait_time = (tokens_needed / self.refill_rate) * self.refill_interval
            time.sleep(min(wait_time, 0.1))

    def get_available_tokens(self) -> float:
        """Get number of available tokens."""
        current_tokens, last_refill = self._get_bucket_state()
        now = time.time()

        time_passed = now - last_refill
        refills = time_passed / self.refill_interval
        tokens_to_add = refills * self.refill_rate

        return min(self.max_tokens, current_tokens + tokens_to_add)

    def reset(self):
        """Reset the bucket to full capacity."""
        self._set_bucket_state(self.max_tokens, time.time())


class RateLimitConfig:
    """Rate limit configurations for different services."""

    GEMINI_EMBEDDING = {
        "max_tokens": 1500,  # 1500 requests per minute
        "refill_rate": 25,  # 25 per second
        "refill_interval": 1.0
    }

    GEMINI_LLM = {
        "max_tokens": 15,  # 15 requests per minute
        "refill_rate": 0.25,  # 0.25 per second
        "refill_interval": 1.0
    }

    SUPABASE_INSERT = {
        "max_tokens": 100,  # 100 inserts per second
        "refill_rate": 100,
        "refill_interval": 1.0
    }


def get_rate_limiter(service_name: str) -> TokenBucketRateLimiter:
    """
    Get rate limiter for a service.

    Args:
        service_name: Name of the service (gemini_embedding, gemini_llm, supabase_insert)

    Returns:
        Configured rate limiter instance
    """
    config_map = {
        "gemini_embedding": RateLimitConfig.GEMINI_EMBEDDING,
        "gemini_llm": RateLimitConfig.GEMINI_LLM,
        "supabase_insert": RateLimitConfig.SUPABASE_INSERT,
    }

    config = config_map.get(service_name)
    if not config:
        raise ValueError(f"Unknown service: {service_name}")

    return TokenBucketRateLimiter(
        key=service_name,
        max_tokens=config["max_tokens"],
        refill_rate=config["refill_rate"],
        refill_interval=config["refill_interval"]
    )
