#!/usr/bin/env python3
"""Generate a secure API key for the FaceDedup API."""

import secrets
import sys


def generate_api_key(prefix: str = "fd") -> str:
    """Generate a 48-char API key with prefix."""
    token = secrets.token_urlsafe(36)
    return f"{prefix}_{token}"


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    keys = []
    for _ in range(count):
        key = generate_api_key()
        keys.append(key)
        print(f"  {key}")

    if count == 1:
        print(f"\nAdd to .env:\n  API_KEYS={keys[0]}")
    else:
        print(f"\nAdd to .env:\n  API_KEYS={','.join(keys)}")
