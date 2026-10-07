from __future__ import annotations

import asyncio

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import FetchRequest, SearchRequest
from aelix_webtool.service import WebService, cancellable


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"query": ""},
        {"query": "   "},
        {"query": 42},
        {"query": "x" * 401},
        {"query": "x\nsecret"},
        {"query": "x", "max_results": True},
        {"query": "x", "max_results": 21},
        {"query": "x", "provider": "unknown"},
        {"query": "x", "time_range": []},
        {"query": "x", "include_domains": "example.com"},
        {"query": "x", "include_domains": ["example.com -site:other.com"]},
        {"query": "x", "include_domains": ["https://example.com/docs"]},
        {"query": "x", "exclude_domains": ["a..com"]},
        {"query": "x", "api_key": "secret"},
    ],
)
def test_invalid_search_arguments_are_rejected(args):
    with pytest.raises(WebToolError) as exc:
        SearchRequest.from_args(args)
    assert exc.value.code == "invalid_arguments"


def test_unicode_query_and_hostname_boundaries():
    request = SearchRequest.from_args(
        {
            "query": "반도체 장비 최신 문서",
            "include_domains": ["Example.COM", "예시.한국"],
            "exclude_domains": ["blocked.example.com"],
        }
    )
    assert request.query == "반도체 장비 최신 문서"
    assert request.accepts_url("https://docs.example.com/a")
    assert not request.accepts_url("https://notexample.com/a")
    assert not request.accepts_url("https://blocked.example.com/a")
    assert not request.accepts_url("https://child.blocked.example.com/a")


@pytest.mark.parametrize(
    "args",
    [
        {"url": "x", "offset": True},
        {"url": "x", "offset": -1},
        {"url": "x", "max_chars": 12001},
        {"url": "x", "headers": {"Authorization": "secret"}},
    ],
)
def test_fetch_arguments_are_bounded(args):
    with pytest.raises(WebToolError):
        FetchRequest.from_args(args)


def test_provider_routing_is_explicit_and_does_not_expose_keys():
    config = Config.from_env({"BRAVE_API_KEY": "secret-brave", "EXA_API_KEY": "secret-exa"})
    assert config.select() == "brave"
    assert config.select("exa") == "exa"
    assert "secret" not in repr(config)
    assert "secret" not in WebService(config).status()
    with pytest.raises(WebToolError, match="TAVILY_API_KEY"):
        config.select("tavily")
    assert (
        Config.from_env(
            {"AELIX_WEB_SEARXNG_URL": "http://127.0.0.1:8080", "BRAVE_API_KEY": "key"}
        ).select()
        == "searxng"
    )


def test_explicit_operator_selection_cannot_silently_degrade():
    config = Config.from_env({"AELIX_WEB_PROVIDER": "tavily", "BRAVE_API_KEY": "key"})
    with pytest.raises(WebToolError) as exc:
        config.select()
    assert exc.value.code == "not_configured"
    assert config.select("brave") == "brave"


async def test_offline_blocks_both_tools_before_network():
    class NoNetwork:
        async def request(self, *args, **kwargs):
            pytest.fail("offline tool performed network I/O")

    service = WebService(Config(offline=True), NoNetwork())
    for operation in (
        service.search(SearchRequest("aelix")),
        service.fetch(FetchRequest("https://example.com")),
    ):
        with pytest.raises(WebToolError) as exc:
            await operation
        assert exc.value.code == "offline"


async def test_abort_cancels_and_drains_the_operation():
    started, cleaned, signal = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def operation():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    task = asyncio.create_task(cancellable(operation, signal))
    await started.wait()
    signal.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()


async def test_pre_aborted_signal_performs_no_work():
    signal = asyncio.Event()
    signal.set()

    async def operation():
        pytest.fail("pre-aborted operation started")

    with pytest.raises(asyncio.CancelledError):
        await cancellable(operation, signal)


async def test_parent_task_cancellation_drains_child():
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def operation():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    task = asyncio.create_task(cancellable(operation, asyncio.Event()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()


async def test_awaitable_abort_signal_matches_host_contract():
    class Signal:
        aborted = True

        async def wait(self):
            return

    with pytest.raises(asyncio.CancelledError):
        await cancellable(lambda: asyncio.sleep(0), Signal())
