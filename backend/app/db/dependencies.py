"""Database and Supabase dependencies."""

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def get_supabase_admin_client() -> Any:
    """Return a Supabase client using the service role key for trusted backend checks."""
    from supabase import create_client

    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


@lru_cache
def get_supabase_anon_client() -> Any:
    """Return a Supabase client using the public anon key for user-facing auth flows."""
    from supabase import create_client

    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache
def get_redis_client() -> Any:
    """Return a Redis client for streaming/cache features."""
    from redis import Redis

    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
    )
