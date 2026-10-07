from __future__ import annotations

import asyncio

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import FetchRequest
from aelix_webtool.network import HttpResponse
from aelix_webtool.service import WebService


class ChangingHttp:
    timeout = 25.0

    def __init__(self):
        self.calls = 0
        self.content = "original documentation " * 40

    async def request(self, *args, **kwargs):
        self.calls += 1
        await asyncio.sleep(0)
        return HttpResponse(
            "https://example.com/final", 200, "text/plain", "utf-8", self.content.encode()
        )


async def test_additional_offsets_read_the_original_snapshot_without_network():
    http = ChangingHttp()
    service = WebService(Config(), http)
    first = await service.fetch(FetchRequest("https://example.com/page", max_chars=100))
    http.content = "changed document " * 40
    second = await service.fetch(
        FetchRequest("https://example.com/page", max_chars=100, offset=100)
    )
    assert http.calls == 1
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["content_hash"] == second["content_hash"]
    assert second["cached"] is True


async def test_concurrent_fetch_and_redirect_alias_share_the_committed_snapshot():
    http = ChangingHttp()
    service = WebService(Config(), http)
    results = await asyncio.gather(
        *(service.fetch(FetchRequest("https://example.com/page")) for _ in range(3))
    )
    alias = await service.fetch(FetchRequest("https://example.com/final"))
    assert http.calls == 1
    assert len({r["snapshot_id"] for r in [*results, alias]}) == 1


async def test_refresh_preserves_the_previous_immutable_content():
    from aelix_webtool.models import ReadRequest

    http = ChangingHttp()
    service = WebService(Config(), http)
    first = await service.fetch(FetchRequest("https://example.com/page"))
    http.content = "new content " * 30
    refreshed = await service.fetch(
        FetchRequest.from_args({"url": "https://example.com/page", "refresh": True})
    )
    old = service.read(ReadRequest.from_args({"snapshot_id": first["snapshot_id"]}))
    assert http.calls == 2 and first["snapshot_id"] != refreshed["snapshot_id"]
    assert "original documentation" in old["content"]
    assert first["content_hash"] != refreshed["content_hash"]


def test_store_expiry_eviction_and_byte_limit():
    from aelix_webtool.store import SnapshotStore

    clock = [0.0]
    store = SnapshotStore(max_entries=2, max_bytes=5000, ttl_seconds=10, clock=lambda: clock[0])
    first = store.put(
        url="https://example.com/1",
        requested_url="https://example.com/1",
        title="One",
        content="first",
        content_type="text/plain",
        format="text",
    )
    second = store.put(
        url="https://example.com/2",
        requested_url="https://example.com/2",
        title="Two",
        content="second",
        content_type="text/plain",
        format="text",
    )
    store.get(first.snapshot_id)
    third = store.put(
        url="https://example.com/3",
        requested_url="https://example.com/3",
        title="Three",
        content="third",
        content_type="text/plain",
        format="text",
    )
    with pytest.raises(WebToolError):
        store.get(second.snapshot_id)
    assert store.get(first.snapshot_id).content == "first"
    assert store.get(third.snapshot_id).content == "third"
    clock[0] = 10.1
    with pytest.raises(WebToolError):
        store.get(first.snapshot_id)
    assert store.by_url("https://example.com/3") is None
    with pytest.raises(WebToolError) as exc:
        store.put(
            url="https://example.com/big",
            requested_url="https://example.com/big",
            title="Big",
            content="가" * 5000,
            content_type="text/plain",
            format="text",
        )
    assert exc.value.code == "snapshot_too_large"


async def test_session_reset_prevents_an_inflight_publisher_and_old_ids():
    from aelix_webtool.models import ReadRequest

    http = ChangingHttp()
    service = WebService(Config(), http)
    first = await service.fetch(FetchRequest("https://example.com/page"))
    service.reset()
    with pytest.raises(WebToolError):
        service.read(ReadRequest(first["snapshot_id"]))
    started, release = asyncio.Event(), asyncio.Event()

    class SlowHttp:
        timeout = 25.0

        async def request(self, *args, **kwargs):
            started.set()
            await release.wait()
            return HttpResponse(
                "https://example.com/slow", 200, "text/plain", "utf-8", b"old session content"
            )

    service.http = SlowHttp()
    task = asyncio.create_task(service.fetch(FetchRequest("https://example.com/slow")))
    await started.wait()
    service.reset()
    release.set()
    with pytest.raises(WebToolError) as exc:
        await task
    assert exc.value.code == "session_changed"
    assert service.store.by_url("https://example.com/slow") is None


async def test_cancel_during_extraction_never_publishes_a_snapshot(monkeypatch):
    import threading

    entered, release = threading.Event(), threading.Event()

    def extract(_response):
        entered.set()
        release.wait(timeout=1)
        return "Document", "Late extractor output", "text"

    monkeypatch.setattr("aelix_webtool.service.extract_page", extract)
    service = WebService(Config(), ChangingHttp())
    task = asyncio.create_task(service.fetch(FetchRequest("https://example.com/page")))
    while not entered.is_set():
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    await asyncio.sleep(0.01)
    assert service.store.size_bytes == 0
