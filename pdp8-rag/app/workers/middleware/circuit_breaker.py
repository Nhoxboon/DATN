"""Circuit breaker middleware for Celery tasks."""

import time
from enum import Enum
from typing import Callable, Any
from functools import wraps
import redis
from app.core.config import get_settings

settings = get_settings()


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit is open."""
    pass


class CircuitBreaker:
    """Circuit breaker implementation using Redis for state management."""

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        timeout: int = 60,
        half_open_max_calls: int = 3
    ):
        """
        Initialize circuit breaker.

        Args:
            service_name: Name of the service to protect
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Max calls to allow in HALF_OPEN state
        """
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_max_calls = half_open_max_calls
        redis_url = settings.redis_url
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.state_key = f"circuit_breaker:{service_name}:state"
        self.failure_count_key = f"circuit_breaker:{service_name}:failure_count"
        self.last_failure_key = f"circuit_breaker:{service_name}:last_failure"
        self.half_open_calls_key = f"circuit_breaker:{service_name}:half_open_calls"

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        state = self.redis_client.get(self.state_key)
        if not state:
            return CircuitState.CLOSED
        return CircuitState(state)

    def set_state(self, state: CircuitState):
        """Set circuit state."""
        self.redis_client.set(self.state_key, state.value)

    def get_failure_count(self) -> int:
        """Get current failure count."""
        count = self.redis_client.get(self.failure_count_key)
        return int(count) if count else 0

    def increment_failure(self):
        """Increment failure counter."""
        self.redis_client.incr(self.failure_count_key)
        self.redis_client.set(self.last_failure_key, str(time.time()))

    def reset_failure_count(self):
        """Reset failure counter."""
        self.redis_client.delete(self.failure_count_key)
        self.redis_client.delete(self.last_failure_key)

    def should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        last_failure = self.redis_client.get(self.last_failure_key)
        if not last_failure:
            return True
        return time.time() - float(last_failure) >= self.timeout

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        state = self.get_state()

        if state == CircuitState.OPEN:
            if self.should_attempt_reset():
                self.set_state(CircuitState.HALF_OPEN)
                self.redis_client.set(self.half_open_calls_key, "0")
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker is OPEN for {self.service_name}"
                )

        if state == CircuitState.HALF_OPEN:
            calls = int(self.redis_client.get(self.half_open_calls_key) or 0)
            if calls >= self.half_open_max_calls:
                raise CircuitBreakerOpen(
                    f"Circuit breaker is HALF_OPEN and max calls reached for {self.service_name}"
                )
            self.redis_client.incr(self.half_open_calls_key)

        try:
            result = func(*args, **kwargs)

            if state == CircuitState.HALF_OPEN:
                self.set_state(CircuitState.CLOSED)
                self.reset_failure_count()
                self.redis_client.delete(self.half_open_calls_key)

            return result

        except Exception as e:
            self.increment_failure()
            failure_count = self.get_failure_count()

            if failure_count >= self.failure_threshold:
                self.set_state(CircuitState.OPEN)

            raise e


def circuit_breaker(
    service_name: str,
    failure_threshold: int = 5,
    timeout: int = 60,
    half_open_max_calls: int = 3
):
    """
    Decorator to add circuit breaker to a function.

    Args:
        service_name: Name of the service
        failure_threshold: Failures before opening
        timeout: Recovery timeout in seconds
        half_open_max_calls: Max calls in half-open state
    """
    def decorator(func):
        breaker = CircuitBreaker(
            service_name,
            failure_threshold,
            timeout,
            half_open_max_calls
        )

        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)

        return wrapper
    return decorator
