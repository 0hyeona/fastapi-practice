"""Bounded, credential-scoped GET cache with conditional revalidation."""
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from app.services.github_rate_limit import credential_key

FRESH_SECONDS = 30
RETAIN_SECONDS = 600
MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRY_BYTES = 1024 * 1024
MAX_ENTRIES = 256
_entries = OrderedDict()
_lock = threading.Lock()


@dataclass(frozen=True)
class Entry:
    body: bytes
    has_next: bool
    etag: str | None
    stored_at: float

    def result(self):
        # Each caller gets its own data; diff enrichment cannot mutate the cache.
        return json.loads(self.body), self.has_next

    def fresh(self):
        return time.monotonic() - self.stored_at < FRESH_SECONDS


def key(headers, repository, path, params):
    return (credential_key(headers), repository.lower(), path,
            tuple(sorted((str(k), str(v)) for k, v in (params or {}).items())))


def lookup(cache_key):
    with _lock:
        entry = _entries.get(cache_key)
        if entry and time.monotonic() - entry.stored_at >= RETAIN_SECONDS:
            _entries.pop(cache_key, None)
            return None
        if entry:
            _entries.move_to_end(cache_key)
        return entry


def save(cache_key, data, has_next, etag):
    body = json.dumps(data, ensure_ascii=False).encode()
    if len(body) > MAX_ENTRY_BYTES:
        return
    with _lock:
        _entries[cache_key] = Entry(body, has_next, etag, time.monotonic())
        _entries.move_to_end(cache_key)
        total = sum(len(entry.body) for entry in _entries.values())
        while len(_entries) > MAX_ENTRIES or total > MAX_BYTES:
            _, entry = _entries.popitem(last=False)
            total -= len(entry.body)
