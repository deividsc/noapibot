"""
Engram KV client for noapibot GCP.
Wraps the Engram HTTP API (POST /memory, GET /memory/{key}, GET /memory/search).
Authenticates via GCP Identity Token when running in Cloud Run.
Falls back to no-auth for local development.
"""
import json
import os
import urllib.request

import httpx

ENGRAM_URL = os.environ.get("ENGRAM_URL", "")
_TIMEOUT = 30


def _auth_headers(url: str) -> dict:
    """Get GCP Identity Token for Cloud Run service-to-service auth."""
    try:
        meta_url = (
            "http://metadata.google.internal/computeMetadata/v1/instance"
            f"/service-accounts/default/identity?audience={url}"
        )
        req = urllib.request.Request(meta_url, headers={"Metadata-Flavor": "Google"})
        token = urllib.request.urlopen(req, timeout=5).read().decode()
        return {"Authorization": f"Bearer {token}"}
    except Exception:
        return {}  # local dev without metadata server


async def engram_read(key: str) -> str:
    """Read a value from Engram KV. Returns '' if not found."""
    if not ENGRAM_URL:
        return ""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        r = await http.get(
            f"{ENGRAM_URL}/memory/{key}",
            headers=_auth_headers(ENGRAM_URL),
        )
        if r.status_code == 404:
            return ""
        r.raise_for_status()
        return r.json().get("value", "")


async def engram_write(key: str, value: str, tags: list[str] | None = None) -> None:
    """Write a value to Engram KV."""
    if not ENGRAM_URL:
        return
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        r = await http.post(
            f"{ENGRAM_URL}/memory",
            json={"key": key, "value": value, "tags": tags or []},
            headers=_auth_headers(ENGRAM_URL),
        )
        r.raise_for_status()


async def engram_search(q: str, limit: int = 5) -> list[dict]:
    """Full-text search in Engram KV. Returns list of {key, value, tags}."""
    if not ENGRAM_URL:
        return []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        r = await http.get(
            f"{ENGRAM_URL}/memory/search",
            params={"q": q, "limit": limit},
            headers=_auth_headers(ENGRAM_URL),
        )
        r.raise_for_status()
        return r.json()
