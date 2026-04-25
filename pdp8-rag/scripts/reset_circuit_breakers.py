#!/usr/bin/env python3
"""Script to reset all circuit breakers in Redis."""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import get_settings
import redis


def main():
    """Reset all circuit breakers."""
    settings = get_settings()

    # Connect to Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    print("=" * 60)
    print("Resetting Circuit Breakers")
    print("=" * 60)
    print()

    # Find all circuit breaker keys
    pattern = "circuit_breaker:*"
    keys = redis_client.keys(pattern)

    if not keys:
        print("No circuit breakers found.")
        return

    # Group keys by service name
    services = {}
    for key in keys:
        parts = key.split(":")
        if len(parts) >= 3:
            service_name = parts[1]
            key_type = parts[2] if len(parts) > 2 else "unknown"
            if service_name not in services:
                services[service_name] = {}
            services[service_name][key_type] = key

    print(f"Found {len(services)} circuit breaker service(s):")
    for service_name, service_keys in services.items():
        state_key = service_keys.get("state")
        state = redis_client.get(state_key) if state_key else "unknown"
        print(f"  - {service_name}: {state}")

    print()
    print("Deleting all circuit breaker states...")

    deleted = redis_client.delete(*keys) if keys else 0

    print(f"✓ Deleted {deleted} circuit breaker(s)")
    print()
    print("All circuit breakers have been reset to CLOSED state.")
    print("=" * 60)


if __name__ == "__main__":
    main()
