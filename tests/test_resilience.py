from __future__ import annotations

import asyncio
import json

import pytest

from aelix_webtool.config import Config
from aelix_webtool.errors import WebToolError
from aelix_webtool.models import SearchRequest
from aelix_webtool.network import HttpResponse
from aelix_webtool.service import WebService


class ScriptedHttp:
    timeout = 25.0

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((url, kwargs))
        value = next(self.responses)
        if isinstance(value, BaseException):
            raise value
        return HttpResponse(url, 200, "application/json", "utf-8", json.dumps(value).encode())


def empty(provider):
    return {"type": "search", "web": {"results": []}} if provider == "brave" else {"results": []}


async def test_operator_retry_is_bounded_and_recorded():
    http = ScriptedHttp(
        [WebToolError("rate_limit", "429", retryable=True, retry_after_seconds=0), empty("brave")]
    )
    result = await WebService(Config(keys={"brave": "key"}, retries=1), http).search(
        SearchRequest("x")
    )
    assert len(http.calls) == 2 and result["provider"] == "brave"
    assert [a["outcome"] for a in result["attempts"]] == ["error", "success"]


async def test_fallback_is_operator_enumerated_and_credential_bound():
    http = ScriptedHttp([WebToolError("http_error", "503", retryable=True), empty("tavily")])
    cfg = Config(
        keys={"brave": "brave-secret", "tavily": "tavily-secret"}, fallback_providers=("tavily",)
    )
    result = await WebService(cfg, http).search(SearchRequest("x"))
    assert result["provider"] == "tavily" and len(http.calls) == 2
    assert http.calls[0][1]["headers"] == {"X-Subscription-Token": "brave-secret"}
    assert http.calls[1][1]["headers"] == {"Authorization": "Bearer tavily-secret"}
    assert "secret" not in json.dumps(result)


async def test_explicit_provider_never_switches_even_with_operator_route():
    http = ScriptedHttp([WebToolError("http_error", "503", retryable=True)])
    cfg = Config(keys={"brave": "key", "tavily": "key2"}, fallback_providers=("tavily",))
    with pytest.raises(WebToolError) as exc:
        await WebService(cfg, http).search(SearchRequest("x", provider="brave"))
    assert len(http.calls) == 1
    assert exc.value.to_dict()["attempts"][0]["provider"] == "brave"


def test_status_never_echoes_invalid_provider_or_route_secrets():
    service = WebService(
        Config(
            provider="not-a-provider",
            keys={"brave": "credential"},
            fallback_providers=("credential",),
        )
    )
    assert "credential" not in service.status()


@pytest.mark.parametrize(
    "code",
    [
        "authorization",
        "invalid_arguments",
        "configuration",
        "blocked_url",
        "provider_blocked",
        "unsupported_filter",
        "invalid_response",
    ],
)
async def test_fail_closed_errors_do_not_retry_or_fail_over(code):
    http = ScriptedHttp([WebToolError(code, "Refused", retryable=True)])
    cfg = Config(keys={"brave": "key", "tavily": "key2"}, retries=1, fallback_providers=("tavily",))
    with pytest.raises(WebToolError) as exc:
        await WebService(cfg, http).search(SearchRequest("x"))
    assert exc.value.code == code and len(http.calls) == 1


async def test_long_retry_after_is_not_ignored_or_waited_past_budget():
    http = ScriptedHttp(
        [WebToolError("rate_limit", "Wait", retryable=True, retry_after_seconds=60)]
    )
    service = WebService(Config(keys={"brave": "key"}, retries=1), http)
    with pytest.raises(WebToolError):
        await service.search(SearchRequest("one"))
    with pytest.raises(WebToolError) as exc:
        await service.search(SearchRequest("two"))
    assert exc.value.retry_after_seconds > 50 and len(http.calls) == 1


async def test_deadline_and_abort_include_retry_wait():
    http = ScriptedHttp([WebToolError("rate_limit", "Wait", retryable=True, retry_after_seconds=1)])
    http.timeout = 0.02
    with pytest.raises(WebToolError) as exc:
        await WebService(Config(keys={"brave": "key"}, retries=1), http).search(SearchRequest("x"))
    assert exc.value.code == "timeout" and len(http.calls) == 1
    signal = asyncio.Event()
    http2 = ScriptedHttp(
        [WebToolError("rate_limit", "Wait", retryable=True, retry_after_seconds=1)]
    )
    task = asyncio.create_task(
        WebService(Config(keys={"brave": "key"}, retries=1), http2).search(
            SearchRequest("x"), signal
        )
    )
    while not http2.calls:
        await asyncio.sleep(0)
    signal.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(http2.calls) == 1


@pytest.mark.parametrize(
    "fallbacks", [("tavily",), ("brave",), ("duckduckgo", "duckduckgo"), ("unknown",)]
)
async def test_invalid_or_unavailable_routes_fail_before_any_request(fallbacks):
    http = ScriptedHttp([])
    with pytest.raises(WebToolError):
        await WebService(Config(keys={"brave": "key"}, fallback_providers=fallbacks), http).search(
            SearchRequest("x")
        )
    assert http.calls == []
