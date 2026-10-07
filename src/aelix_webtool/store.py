"""Bounded immutable snapshots owned by one service/session; no I/O."""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from array import array
from bisect import bisect_right
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .errors import WebToolError


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    requested_url: str
    url: str
    title: str
    content: str = field(repr=False)
    content_type: str
    format: str
    content_hash: str
    retrieved_at: str
    expires_at: float
    line_starts: bytes = field(repr=False)
    size_bytes: int

    def line(self, offset: int) -> int:
        return bisect_right(memoryview(self.line_starts).cast("I"), offset)


class SnapshotStore:
    def __init__(
        self,
        *,
        max_entries: int = 32,
        max_bytes: int = 16_000_000,
        ttl_seconds: float = 1800,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1 or max_bytes < 1 or ttl_seconds <= 0:
            raise ValueError("Snapshot limits must be positive")
        self.max_entries, self.max_bytes, self.ttl_seconds = max_entries, max_bytes, ttl_seconds
        self.clock = clock
        self._entries: OrderedDict[str, Snapshot] = OrderedDict()
        self._aliases: dict[str, str] = {}
        self.size_bytes = 0

    def clear(self) -> None:
        self._entries.clear()
        self._aliases.clear()
        self.size_bytes = 0

    def _remove(self, key: str) -> None:
        item = self._entries.pop(key)
        self.size_bytes -= item.size_bytes
        for url in {item.url, item.requested_url}:
            if self._aliases.get(url) == key:
                del self._aliases[url]

    def _expire(self) -> None:
        now = self.clock()
        for key, item in list(self._entries.items()):
            if item.expires_at <= now:
                self._remove(key)

    def get(self, key: str) -> Snapshot:
        if not isinstance(key, str) or not re.fullmatch(r"snap-[A-Za-z0-9_-]{24}", key):
            raise WebToolError("invalid_arguments", "Use the snapshot_id returned by web_fetch.")
        self._expire()
        item = self._entries.get(key)
        if item is None:
            raise WebToolError(
                "snapshot_not_found",
                "Snapshot is missing, expired or belongs to another session. Fetch the URL again explicitly.",
            )
        self._entries.move_to_end(key)
        return item

    def by_url(self, url: str) -> Snapshot | None:
        self._expire()
        key = self._aliases.get(url)
        return self.get(key) if key else None

    def put(
        self,
        *,
        requested_url: str,
        url: str,
        title: str,
        content: str,
        content_type: str,
        format: str,
    ) -> Snapshot:
        encoded = content.encode()
        if len(encoded) > 2_000_000:
            raise WebToolError(
                "snapshot_too_large", "Extracted text exceeds the 2 MB snapshot limit."
            )
        offsets = array("I", [0])
        offsets.extend(i + 1 for i, c in enumerate(content) if c == "\n")
        # Immutable compact index; account for it as well as text and metadata.
        lines = offsets.tobytes()
        size = (
            len(encoded)
            + len(lines)
            + len((url + requested_url + title + content_type + format).encode())
            + 256
        )
        if size > self.max_bytes:
            raise WebToolError(
                "snapshot_too_large", "The snapshot exceeds this session's cache capacity."
            )
        self._expire()
        while self._entries and (
            len(self._entries) >= self.max_entries or self.size_bytes + size > self.max_bytes
        ):
            self._remove(next(iter(self._entries)))
        key = "snap-" + secrets.token_urlsafe(18)
        item = Snapshot(
            key,
            requested_url,
            url,
            title,
            content,
            content_type,
            format,
            hashlib.sha256(encoded).hexdigest(),
            datetime.now(UTC).isoformat(),
            self.clock() + self.ttl_seconds,
            lines,
            size,
        )
        self._entries[key] = item
        self._aliases[requested_url] = key
        self._aliases[url] = key
        self.size_bytes += size
        return item
