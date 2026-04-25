"""Distributed lock implementation using Redis."""

import time
import uuid
from contextlib import contextmanager
from typing import Optional
import redis
from app.core.config import get_settings

settings = get_settings()


class DistributedLock:
    """Redis-based distributed lock for preventing race conditions."""

    def __init__(self, lock_name: str, timeout: int = 3600, retry_delay: float = 0.1):
        """
        Initialize distributed lock.

        Args:
            lock_name: Name of the lock
            timeout: Lock timeout in seconds
            retry_delay: Delay between lock acquisition retries
        """
        self.lock_name = f"lock:{lock_name}"
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.lock_id = str(uuid.uuid4())
        redis_url = settings.redis_url
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

    def acquire(self, blocking: bool = True, timeout: Optional[int] = None) -> bool:
        """
        Acquire the lock.

        Args:
            blocking: If True, wait until lock is available
            timeout: Max seconds to wait (only if blocking=True)

        Returns:
            True if lock acquired, False otherwise
        """
        start_time = time.time()

        while True:
            # Try to set the lock with NX (only if not exists) and EX (expiration)
            acquired = self.redis_client.set(
                self.lock_name,
                self.lock_id,
                nx=True,
                ex=self.timeout
            )

            if acquired:
                return True

            if not blocking:
                return False

            if timeout and (time.time() - start_time) >= timeout:
                return False

            time.sleep(self.retry_delay)

    def release(self) -> bool:
        """
        Release the lock safely (only if we own it).

        Returns:
            True if released, False if we don't own the lock
        """
        # Lua script to atomically check and delete
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        result = self.redis_client.eval(lua_script, 1, self.lock_name, self.lock_id)
        return bool(result)

    def extend(self, additional_time: int) -> bool:
        """
        Extend the lock timeout.

        Args:
            additional_time: Additional seconds to extend

        Returns:
            True if extended successfully
        """
        # Get current value
        current_value = self.redis_client.get(self.lock_name)

        if current_value != self.lock_id:
            return False

        # Extend expiration
        return bool(self.redis_client.expire(self.lock_name, self.timeout + additional_time))

    def is_locked(self) -> bool:
        """Check if the lock is currently held."""
        return bool(self.redis_client.exists(self.lock_name))

    def get_lock_holder(self) -> Optional[str]:
        """Get the ID of the current lock holder."""
        result = self.redis_client.get(self.lock_name)
        return str(result) if result is not None else None


@contextmanager
def distributed_lock(lock_name: str, timeout: int = 3600, blocking: bool = True, acquire_timeout: Optional[int] = None):
    """
    Context manager for distributed lock.

    Args:
        lock_name: Name of the lock
        timeout: Lock timeout in seconds
        blocking: Wait for lock if True
        acquire_timeout: Max seconds to wait for acquisition

    Raises:
        RuntimeError: If lock cannot be acquired (when blocking=False or timeout exceeded)

    Example:
        with distributed_lock("document:sample.pdf"):
            # Critical section
            process_document()
    """
    lock = DistributedLock(lock_name, timeout)

    acquired = lock.acquire(blocking=blocking, timeout=acquire_timeout)

    if not acquired:
        raise RuntimeError(f"Could not acquire lock: {lock_name}")

    try:
        yield lock
    finally:
        lock.release()
