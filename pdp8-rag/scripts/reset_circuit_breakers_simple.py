#!/usr/bin/env python3
"""Simple script to reset all circuit breakers in Redis."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import get_settings
import redis


def main():
    """Reset all circuit breakers."""
    settings = get_settings()
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    print("=" * 60)
    print("Resetting Circuit Breakers")
    print("=" * 60)
    print()

    pattern = "circuit_breaker:*"
    keys = redis_client.keys(pattern)

    if not keys:
        print("No circuit breakers found.")
        print("=" * 60)
        return

    print(f"Found {len(keys)} circuit breaker key(s)")
    print()
    print("Deleting all circuit breaker states...")

    deleted = redis_client.delete(*keys)

    print(f"✓ Deleted {deleted} key(s)")
    print()
    print("All circuit breakers have been reset to CLOSED state.")
    print("=" * 60)


if __name__ == "__main__":
    main()
