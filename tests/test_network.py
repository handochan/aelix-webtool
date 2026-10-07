from __future__ import annotations

import asyncio
import gzip
import socket
import zlib

import pytest
import pytest_asyncio
from aiohttp import web

from aelix_webtool.errors import WebToolError
from aelix_webtool.network import (
    HttpClient,
    PublicResolver,
    check_status,
    is_public_address,
    validate_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/page",
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fe80::1%25en0]/",
        "http://localhost/",
        "http://box.local/",
        "http://example.com:8080/",
        "https://user:password@example.com/",
        "https://example.com/\nsecret",
        "https://example.com:invalid/",
        "https://example.com/ space",
    ],
)
def test_unsafe_url_forms_are_rejected(url):
    with pytest.raises(WebToolError):
        validate_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",
        "127.0.0.1",
        "10.0.0.1",
        "192.168.0.1",
        "172.16.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "224.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "2002:7f00:1::",
        "invalid",
    ],
)
def test_special_addresses_are_blocked(address):
    assert not is_public_address(address)


def test_public_literals_and_idna_normalize_consistently():
    assert is_public_address("8.8.8.8")
    assert is_public_address("2606:4700:4700::1111")
    assert validate_url("https://예시.한국/a#fragment").endswith("/a")
    assert validate_url("https://8.8.8.8/") == "https://8.8.8.8/"


@pytest.mark.parametrize("host", ["2130706433", "127.1", "0177.0.0.1", "0x7f000001", "0x7f.0.0.1"])
def test_legacy_numeric_addresses_are_blocked_before_connector_shortcuts(host):
    with pytest.raises(WebToolError) as exc:
        validate_url(f"http://{host}/")
    assert exc.value.code == "blocked_url"


def dns_record(host, address, port=80):
    return {
        "hostname": host,
        "host": address,
        "port": port,
        "family": socket.AF_INET,
        "proto": 0,
        "flags": 0,
    }


async def test_connector_resolver_rejects_mixed_public_private_answers(monkeypatch):
    resolver = PublicResolver()

    async def resolve(host, port, family):
        return [dns_record(host, "8.8.8.8", port), dns_record(host, "127.0.0.1", port)]

    monkeypatch.setattr(resolver._delegate, "resolve", resolve)
    try:
        with pytest.raises(WebToolError) as exc:
            await resolver.resolve("rebind.example", 80)
        assert exc.value.code == "blocked_url"
    finally:
        await resolver.close()


async def test_resolver_returns_validated_addresses_without_second_lookup(monkeypatch):
    resolver = PublicResolver()
    calls = []

    async def resolve(host, port, family):
        calls.append((host, port))
        if len(calls) > 1:
            return [dns_record(host, "127.0.0.1", port)]
        return [dns_record(host, "8.8.8.8", port)]

    monkeypatch.setattr(resolver._delegate, "resolve", resolve)
    try:
        records = await resolver.resolve("rebind.example", 443)
        assert len(calls) == 1 and records[0]["host"] == "8.8.8.8"
        with pytest.raises(WebToolError):
            await resolver.resolve("rebind.example", 443)
    finally:
        await resolver.close()


@pytest_asyncio.fixture
async def local_server():
    hits = []

    async def handler(request):
        hits.append((request.path, dict(request.headers), dict(request.query)))
        if request.path == "/redirect":
            raise web.HTTPFound("/page")
        if request.path == "/private":
            raise web.HTTPFound("http://127.0.0.1/private-target")
        if request.path == "/loop":
            raise web.HTTPFound("/loop")
        if request.path == "/api-redirect":
            raise web.HTTPFound("/capture")
        if request.path == "/large":
            return web.Response(text="x" * 2_000_001)
        if request.path == "/stream":
            response = web.StreamResponse(headers={"Content-Type": "text/plain"})
            await response.prepare(request)
            try:
                for _ in range(130):
                    await response.write(b"x" * 16384)
                await response.write_eof()
            except ConnectionResetError:
                pass
            return response
        if request.path.startswith("/slow"):
            await asyncio.sleep(0.15)
            if request.path == "/slow1":
                raise web.HTTPFound("/slow2")
            return web.Response(text="done")
        if request.path == "/pdf":
            return web.Response(body=b"%PDF fake", content_type="application/pdf")
        if request.path == "/compressed":
            return web.Response(
                body=b"compressed",
                headers={"Content-Encoding": "gzip", "Content-Type": "text/plain"},
            )
        if request.path in {
            "/gzip",
            "/deflate",
            "/raw-deflate",
            "/bomb",
            "/truncated-gzip",
            "/joined-gzip",
        }:
            text = "장비 documentation " * 50
            data = text.encode()
            encoding = "gzip"
            if request.path == "/bomb":
                data = b"x" * 2_000_001
            if request.path == "/deflate":
                encoding, payload = "deflate", zlib.compress(data)
            elif request.path == "/raw-deflate":
                compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
                encoding, payload = "deflate", compressor.compress(data) + compressor.flush()
            else:
                payload = gzip.compress(data)
                if request.path == "/truncated-gzip":
                    payload = payload[:-8]
                if request.path == "/joined-gzip":
                    payload += gzip.compress(b"second")
            return web.Response(
                body=payload,
                headers={"Content-Encoding": encoding, "Content-Type": "text/plain; charset=utf-8"},
            )
        if request.path == "/429":
            return web.Response(status=429, text="SECRET-KEY from upstream")
        if request.path == "/search":
            return web.json_response(
                {
                    "results": [
                        {
                            "title": "fixture",
                            "url": "https://example.com",
                            "content": "search fixture",
                        }
                    ]
                }
            )
        return web.Response(
            text="<title>Fixture</title><main>안녕하세요</main>", content_type="text/html"
        )

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield port, hits
    finally:
        await runner.cleanup()


@pytest_asyncio.fixture
async def public_fixture(local_server, monkeypatch):
    port, hits = local_server

    # Route a synthetic public hostname to the test server's socket. This is
    # confined to HTTP-behavior tests; production URL validation remains active.
    # Resolver/address policy is tested independently above and below.
    async def resolve(_self, host, _port, family=socket.AF_INET):
        return [dns_record(host, "127.0.0.1", port)]

    monkeypatch.setattr(PublicResolver, "resolve", resolve)
    return "http://fixture.example", hits


async def test_real_http_redirect_and_headers(public_fixture, monkeypatch):
    base, hits = public_fixture
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    response = await HttpClient().request("GET", base + "/redirect", fetch=True)
    assert response.url == base + "/page"
    assert "안녕하세요" in response.body.decode()
    assert [r[0] for r in hits] == ["/redirect", "/page"]
    assert hits[0][1]["Accept-Encoding"] == "gzip, deflate"
    assert "Cookie" not in hits[0][1]


async def test_redirect_to_private_literal_is_blocked_before_second_request(public_fixture):
    base, hits = public_fixture
    with pytest.raises(WebToolError) as exc:
        await HttpClient().request("GET", base + "/private", fetch=True)
    assert exc.value.code == "blocked_url"
    assert [r[0] for r in hits] == ["/private"]


async def test_real_connector_dns_policy_blocks_request_to_local_server(local_server, monkeypatch):
    from aiohttp.resolver import ThreadedResolver

    port, hits = local_server

    async def resolve(_self, host, _port, family):
        return [dns_record(host, "127.0.0.1", port)]

    monkeypatch.setattr(ThreadedResolver, "resolve", resolve)
    with pytest.raises(WebToolError) as exc:
        await HttpClient().request("GET", "http://rebind.example/page", fetch=True)
    assert exc.value.code == "blocked_url"
    assert hits == []


async def test_search_api_never_follows_even_same_origin_redirect(public_fixture):
    base, hits = public_fixture
    with pytest.raises(WebToolError) as exc:
        await HttpClient().request(
            "GET", base + "/api-redirect", headers={"Authorization": "Bearer SECRET-KEY"}
        )
    assert exc.value.code == "redirect_refused"
    assert "SECRET-KEY" not in str(exc.value)
    assert [r[0] for r in hits] == ["/api-redirect"]


@pytest.mark.parametrize(
    "path,code",
    [
        ("/large", "response_too_large"),
        ("/stream", "response_too_large"),
        ("/pdf", "unsupported_content"),
        ("/compressed", "invalid_response"),
        ("/bomb", "response_too_large"),
        ("/truncated-gzip", "invalid_response"),
        ("/joined-gzip", "invalid_response"),
        ("/loop", "redirect_limit"),
        ("/429", "rate_limit"),
    ],
)
async def test_real_http_failure_boundaries(public_fixture, path, code):
    base, hits = public_fixture
    with pytest.raises(WebToolError) as exc:
        await HttpClient().request("GET", base + path, fetch=True)
    assert exc.value.code == code
    assert "SECRET-KEY" not in str(exc.value)
    if path == "/loop":
        assert len(hits) == 6


async def test_total_deadline_includes_redirect_chain(public_fixture):
    base, hits = public_fixture
    with pytest.raises(WebToolError) as exc:
        await HttpClient(timeout=0.22).request("GET", base + "/slow1", fetch=True)
    assert exc.value.code == "timeout"
    assert len(hits) == 2


@pytest.mark.parametrize("path", ["/gzip", "/deflate", "/raw-deflate"])
async def test_real_http_decodes_supported_compression(public_fixture, path):
    base, _ = public_fixture
    result = await HttpClient().request("GET", base + path, fetch=True)
    assert result.body.decode() == "장비 documentation " * 50


def test_decoder_handles_split_header_and_bounds_before_allocation():
    from aelix_webtool.compression import BodyDecoder

    payload = zlib.compress("Unicode 장비".encode())
    decoder = BodyDecoder("deflate", 1000)
    result = b"".join(decoder.feed(payload[i : i + 1]) for i in range(len(payload)))
    decoder.finish()
    assert result.decode() == "Unicode 장비"
    with pytest.raises(WebToolError) as exc:
        BodyDecoder("gzip", 1000).feed(gzip.compress(b"a" * 1_000_000))
    assert exc.value.code == "response_too_large"


def test_retry_after_is_exposed_without_error_body():
    with pytest.raises(WebToolError) as exc:
        check_status(429, {"Retry-After": "5", "Authorization": "SECRET"})
    assert exc.value.retry_after_seconds == 5
    assert "SECRET" not in str(exc.value.to_dict())


async def test_parent_cancellation_closes_http_resources(public_fixture):
    base, hits = public_fixture
    task = asyncio.create_task(HttpClient().request("GET", base + "/slow1", fetch=True))
    while not hits:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # A new request still works and the cancelled one never reaches slow2.
    await HttpClient().request("GET", base + "/page", fetch=True)
    assert not any(r[0] == "/slow2" for r in hits)


async def test_private_searxng_is_narrow_and_fetch_cannot_enable_it(local_server):
    from aelix_webtool.config import Config
    from aelix_webtool.models import SearchRequest
    from aelix_webtool.service import WebService

    port, hits = local_server
    base = f"http://127.0.0.1:{port}"
    result = await WebService(Config(searxng_url=base)).search(SearchRequest("aelix 문서"))
    assert result["provider"] == "searxng" and len(result["results"]) == 1
    assert hits[0][2]["q"] == "aelix 문서"
    assert hits[0][2]["format"] == "json"
    with pytest.raises(WebToolError):
        await HttpClient().request("GET", base, fetch=True, allow_private=True)


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "authorization", False),
        (403, "authorization", False),
        (402, "usage_limit", False),
        (433, "usage_limit", False),
        (429, "rate_limit", True),
        (503, "http_error", True),
        (404, "http_error", False),
    ],
)
def test_error_classification(status, code, retryable):
    with pytest.raises(WebToolError) as exc:
        check_status(status)
    assert exc.value.code == code and exc.value.retryable == retryable
