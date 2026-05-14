"""Persistent cache registry using Redis."""

import json
from typing import Optional
from urllib.parse import quote, unquote

from app.db.dependencies import get_redis_client


CACHE_PREFIX = "gemini_cache"
CACHE_MANIFEST_PREFIX = "gemini_cache_manifest"
DOCS_SEGMENT = "docs"


def _encode_cache_part(value: str) -> str:
    return quote(value, safe="")


def _decode_cache_part(value: str) -> str:
    return unquote(value)


def _redis_key(cache_key: str) -> str:
    """Return the Redis key for a cache identifier."""
    return cache_key


def _normalize_doc_names(doc_names: list[str]) -> list[str]:
    return sorted({str(doc_name).strip() for doc_name in doc_names if str(doc_name).strip()})


def build_document_cache_key(notebook_id: str, doc_names: list[str]) -> str:
    """Build a notebook-scoped cache key for one or more documents."""
    return _build_scoped_cache_key(CACHE_PREFIX, notebook_id, doc_names)


def build_document_cache_manifest_key(notebook_id: str, doc_names: list[str]) -> str:
    """Build a notebook-scoped manifest key for one or more documents."""
    return _build_scoped_cache_key(CACHE_MANIFEST_PREFIX, notebook_id, doc_names)


def _build_scoped_cache_key(prefix: str, notebook_id: str, doc_names: list[str]) -> str:
    clean_notebook_id = str(notebook_id).strip()
    clean_doc_names = _normalize_doc_names(doc_names)
    if not clean_notebook_id:
        raise ValueError("notebook_id is required for Gemini cache keys.")
    if not clean_doc_names:
        raise ValueError("At least one document name is required for Gemini cache keys.")

    encoded_notebook = _encode_cache_part(clean_notebook_id)
    encoded_docs = "|".join(_encode_cache_part(doc_name) for doc_name in clean_doc_names)
    return f"{prefix}:{encoded_notebook}:{DOCS_SEGMENT}:{encoded_docs}"


def _document_names_from_cache_key(cache_key: str, notebook_id: str, prefix: str = CACHE_PREFIX) -> list[str]:
    encoded_notebook = _encode_cache_part(str(notebook_id).strip())
    key_prefix = f"{prefix}:{encoded_notebook}:{DOCS_SEGMENT}:"
    if not cache_key.startswith(key_prefix):
        return []

    encoded_docs = cache_key[len(key_prefix):]
    if not encoded_docs:
        return []
    return [_decode_cache_part(part) for part in encoded_docs.split("|") if part]


def get_cache_name(cache_key: str) -> Optional[str]:
    """Get the Gemini cache name from Redis."""
    try:
        client = get_redis_client()
        cache_name = client.get(_redis_key(cache_key))
        return cache_name.decode() if isinstance(cache_name, bytes) else cache_name
    except Exception as e:
        print(f"[CACHE] Error getting cache name: {e}")
        return None


def set_cache_name(cache_key: str, cache_name: str, ttl_seconds: int = 86400):
    """Set a Gemini cache name in Redis with TTL."""
    try:
        client = get_redis_client()
        client.setex(_redis_key(cache_key), ttl_seconds, cache_name)
        print(f"[CACHE] Saved to Redis: {cache_key} -> {cache_name}")
    except Exception as e:
        print(f"[CACHE] Error setting cache name: {e}")


def get_cache_manifest(manifest_key: str) -> list[dict] | None:
    """Get a cached source manifest from Redis."""
    try:
        client = get_redis_client()
        manifest = client.get(_redis_key(manifest_key))
        if not manifest:
            return None
        manifest_text = manifest.decode() if isinstance(manifest, bytes) else manifest
        data = json.loads(manifest_text)
        return data if isinstance(data, list) else None
    except Exception as e:
        print(f"[CACHE] Error getting cache manifest: {e}")
        return None


def set_cache_manifest(manifest_key: str, sources: list[dict], ttl_seconds: int = 86400) -> None:
    """Set a source manifest in Redis with TTL."""
    try:
        client = get_redis_client()
        client.setex(_redis_key(manifest_key), ttl_seconds, json.dumps(sources))
        print(f"[CACHE] Saved manifest to Redis: {manifest_key}")
    except Exception as e:
        print(f"[CACHE] Error setting cache manifest: {e}")


def delete_cache_name(cache_key: str) -> bool:
    """Delete a Gemini cache name from Redis."""
    try:
        client = get_redis_client()
        result = client.delete(_redis_key(cache_key))
        return result > 0
    except Exception as e:
        print(f"[CACHE] Error deleting cache name: {e}")
        return False


def delete_cache_manifest(manifest_key: str) -> bool:
    """Delete a source manifest from Redis."""
    try:
        client = get_redis_client()
        result = client.delete(_redis_key(manifest_key))
        return result > 0
    except Exception as e:
        print(f"[CACHE] Error deleting cache manifest: {e}")
        return False


def invalidate_document_caches(notebook_id: str, document_name: str) -> int:
    """Delete Redis cache pointers for any notebook cache containing document_name."""
    clean_document_name = str(document_name).strip()
    if not str(notebook_id).strip() or not clean_document_name:
        return 0

    encoded_notebook = _encode_cache_part(str(notebook_id).strip())
    patterns = [
        (CACHE_PREFIX, f"{CACHE_PREFIX}:{encoded_notebook}:{DOCS_SEGMENT}:*"),
        (CACHE_MANIFEST_PREFIX, f"{CACHE_MANIFEST_PREFIX}:{encoded_notebook}:{DOCS_SEGMENT}:*"),
    ]

    try:
        client = get_redis_client()
        deleted = 0
        for prefix, pattern in patterns:
            for key in client.scan_iter(match=pattern):
                key_str = key.decode() if isinstance(key, bytes) else str(key)
                doc_names = _document_names_from_cache_key(key_str, notebook_id, prefix)
                if clean_document_name in doc_names:
                    deleted += int(client.delete(key))
        if deleted:
            print(f"[CACHE] Invalidated {deleted} cache(s) for notebook={notebook_id} document={document_name}")
        return deleted
    except Exception as e:
        print(f"[CACHE] Error invalidating document caches: {e}")
        return 0


def list_all_cached_docs() -> dict:
    """List all cached documents from Redis."""
    try:
        client = get_redis_client()
        keys = client.keys(f"{CACHE_PREFIX}:*")
        result = {}
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            cache_name = client.get(key)
            if cache_name:
                cache_name_str = cache_name.decode() if isinstance(cache_name, bytes) else cache_name
                result[key_str] = cache_name_str
        return result
    except Exception as e:
        print(f"[CACHE] Error listing caches: {e}")
        return {}
