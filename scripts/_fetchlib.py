"""Shared helpers for the fetch scripts.

Fetch scripts write raw payloads to data/raw/, which is gitignored. Nothing here
decides what is redistributable; that is the snapshot builder's job. These
helpers only handle politeness, retries and caching so a re-run is cheap.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
UA = "crispr-hindcast/0.1 (public-data research benchmark; contact via repository)"


def client(timeout: float = 180.0) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)


def get_json(c: httpx.Client, url: str, *, params: dict | None = None, tries: int = 4) -> Any:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            r = c.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                continue
            r.raise_for_status()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url} params={params}") from last


def post_json(c: httpx.Client, url: str, payload: dict, *, tries: int = 4) -> Any:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            r = c.post(url, json=payload)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                continue
            r.raise_for_status()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"POST failed after {tries} tries: {url}") from last


def write(rel: str, payload: Any) -> Path:
    out = RAW / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    return out


def read(rel: str) -> Any | None:
    path = RAW / rel
    return json.loads(path.read_text()) if path.exists() else None
