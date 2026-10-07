"""Bounded HTTP with address checks on the resolver the connector actually uses."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urldefrag

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import ThreadedResolver
from yarl import URL

from .errors import WebToolError

REDIRECTS = {301, 302, 303, 307, 308}
FETCH_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "application/json",
}


def is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        # Scope IDs and transition addresses can route into otherwise blocked networks.
        if ip.scope_id or ip.sixtofour or ip.teredo:
            return False
        if ip.ipv4_mapped:
            return is_public_address(str(ip.ipv4_mapped))
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def validate_url(value: str, *, allow_private: bool = False) -> str:
    """Validate the same normalized URL handed to aiohttp, including IP literals."""
    if not value or len(value) > 2048 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise WebToolError(
            "invalid_url", "Use an absolute HTTP(S) URL without whitespace or control characters."
        )
    try:
        url = URL(value)
        host = url.raw_host
        port = url.port
    except (ValueError, UnicodeError):
        raise WebToolError("invalid_url", "The URL is malformed.") from None
    if (
        url.scheme not in {"http", "https"}
        or not host
        or url.user is not None
        or url.password is not None
    ):
        raise WebToolError(
            "invalid_url", "Only absolute HTTP(S) URLs without embedded credentials are supported."
        )
    if not allow_private:
        if port not in {80, 443}:
            raise WebToolError("blocked_url", "Public-page reading supports ports 80 and 443 only.")
        host = host.lower().rstrip(".")
        if host == "localhost" or host.endswith(
            (".localhost", ".local", ".internal", ".invalid", ".test")
        ):
            raise WebToolError(
                "blocked_url", "Local and internal addresses are not supported by web_fetch."
            )
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is None and (
            "%" in host
            or all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", part) for part in host.split("."))
        ):
            # Older connector/socket versions can accept numeric IPv4 forms
            # without invoking the checked DNS resolver. Enforce this here.
            raise WebToolError("blocked_url", "Noncanonical numeric addresses are blocked.")
        if literal is not None and not is_public_address(str(literal)):
            raise WebToolError(
                "blocked_url", "Local, private and special-use addresses are blocked."
            )
    return urldefrag(str(url))[0]


class PublicResolver(AbstractResolver):
    """Return only a fully public DNS answer, then let aiohttp connect to those IPs.

    No separate preflight lookup: validated addresses are the actual connection
    addresses, retaining the original hostname for TLS SNI and Host headers.
    Reject mixed public/private answers instead of filtering the private rows.
    """

    def __init__(self) -> None:
        self._delegate = ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        records = await self._delegate.resolve(host, port, family)
        if not records or any(not is_public_address(record["host"]) for record in records):
            raise WebToolError("blocked_url", "DNS resolved to a private or special-use address.")
        return records

    async def close(self) -> None:
        await self._delegate.close()


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    content_type: str
    charset: str
    body: bytes

    def json(self) -> dict[str, Any]:
        try:
            value = json.loads(self.body)
        except (ValueError, UnicodeError, RecursionError):
            raise WebToolError(
                "invalid_response", "The search provider returned invalid JSON."
            ) from None
        if not isinstance(value, dict):
            raise WebToolError(
                "invalid_response", "The search provider returned an unexpected JSON shape."
            )
        return value


def check_status(status: int) -> None:
    if 200 <= status < 300:
        return
    if status in {401, 403}:
        raise WebToolError(
            "authorization",
            f"The server refused this request (HTTP {status}). Check credentials or access policy.",
        )
    if status == 429:
        raise WebToolError(
            "rate_limit",
            "The server rate limit was reached (HTTP 429). Try again later.",
            retryable=True,
        )
    if status in {402, 432, 433}:
        raise WebToolError(
            "usage_limit", f"The provider's usage or billing limit was reached (HTTP {status})."
        )
    raise WebToolError("http_error", f"The server returned HTTP {status}.", retryable=status >= 500)


class HttpClient:
    def __init__(self, *, timeout: float = 25.0) -> None:
        self.timeout = timeout

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        fetch: bool = False,
        allow_private: bool = False,
    ) -> HttpResponse:
        # Private access is exclusively for an operator-configured SearXNG
        # endpoint. It must never become an option on the model's fetch tool.
        if fetch and allow_private:
            raise WebToolError("blocked_url", "web_fetch cannot access private networks.")
        current = validate_url(url, allow_private=allow_private)
        resolver = None if allow_private else PublicResolver()
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False, limit=4)
        request_headers = {
            "User-Agent": "aelix-webtool/0.1.0",
            "Accept-Encoding": "identity",
            "Accept": "text/html, text/plain, text/markdown, application/json"
            if fetch
            else "application/json",
            **(headers or {}),
        }
        limit = 2_000_000 if fetch else 1_000_000
        try:
            async with (
                asyncio.timeout(self.timeout),
                aiohttp.ClientSession(
                    connector=connector,
                    cookie_jar=aiohttp.DummyCookieJar(),
                    trust_env=False,
                    auto_decompress=False,
                    timeout=aiohttp.ClientTimeout(total=self.timeout, connect=10),
                ) as session,
            ):
                for hop in range(6):
                    async with session.request(
                        method,
                        current,
                        headers=request_headers,
                        params=params,
                        json=json_body,
                        allow_redirects=False,
                    ) as response:
                        if response.status in REDIRECTS:
                            # API credentials are never forwarded to a redirect.
                            if not fetch:
                                raise WebToolError(
                                    "redirect_refused",
                                    "Search API redirects are refused to protect credentials.",
                                )
                            location = response.headers.get("Location")
                            if not location or hop == 5:
                                raise WebToolError(
                                    "redirect_limit", "The page has invalid or too many redirects."
                                )
                            current = validate_url(str(URL(current).join(URL(location))))
                            params = None
                            continue
                        check_status(response.status)
                        if response.headers.get("Content-Encoding", "identity").lower() not in {
                            "",
                            "identity",
                        }:
                            raise WebToolError(
                                "unsupported_encoding",
                                "The server ignored the request for uncompressed content.",
                            )
                        content_type = response.content_type.lower()
                        if fetch and content_type not in FETCH_TYPES:
                            raise WebToolError(
                                "unsupported_content",
                                "Only HTML, plain text, Markdown and JSON pages are supported; PDF and binary content are not.",
                            )
                        if response.content_length is not None and response.content_length > limit:
                            raise WebToolError(
                                "response_too_large",
                                f"The response exceeds the {limit}-byte limit.",
                            )
                        body = bytearray()
                        async for chunk in response.content.iter_chunked(16384):
                            body.extend(chunk)
                            if len(body) > limit:
                                raise WebToolError(
                                    "response_too_large",
                                    f"The response exceeds the {limit}-byte limit.",
                                )
                        return HttpResponse(
                            url=str(response.url),
                            status=response.status,
                            content_type=content_type,
                            charset=response.charset or "utf-8",
                            body=bytes(body),
                        )
                raise WebToolError("redirect_limit", "Too many redirects.")
        except TimeoutError:
            raise WebToolError(
                "timeout", "The web request exceeded its total time limit.", retryable=True
            ) from None
        except (aiohttp.ClientError, OSError, ValueError):
            # Never stringify a client exception: it may carry URLs, headers,
            # keys or an echoed upstream response body.
            raise WebToolError(
                "network_error",
                "The web request failed. Check connectivity and TLS certificates.",
                retryable=True,
            ) from None
        finally:
            await connector.close()
            if resolver is not None:
                await resolver.close()
