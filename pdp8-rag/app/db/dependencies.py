"""Database dependencies for FastAPI dependency injection."""

from functools import lru_cache
from redis import Redis
from supabase import create_client, Client
from app.core.config import get_settings


@lru_cache()
def get_supabase_client() -> Client:
    """
    Get Supabase client with service role (for backend operations).

    Returns:
        Supabase client instance with service role permissions
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


@lru_cache()
def get_redis_client() -> Redis:
    """
    Get Redis client instance.

    Returns:
        Redis client instance
    """
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True
    )
