"""Host-independent request and result contracts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

from .config import PROVIDERS
from .errors import WebToolError

TIME_RANGES = ("day", "week", "month", "year")


def bounded_int(args: dict[str, Any], name: str, default: int, low: int, high: int) -> int:
    value = args.get(name, default)
    if type(value) is not int or not low <= value <= high:
        raise WebToolError("invalid_arguments", f"{name} must be an integer from {low} to {high}.")
    return value


def domains(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 10:
        raise WebToolError("invalid_arguments", f"{name} must be a list of at most 10 hostnames.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise WebToolError("invalid_arguments", f"{name} must contain hostnames.")
        try:
            host = item.strip().rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError:
            host = ""
        if len(host) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
            raise WebToolError(
                "invalid_arguments",
                f"{name} accepts hostnames without schemes, paths or operators.",
            )
        if any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in host.split(".")
        ):
            raise WebToolError("invalid_arguments", f"{name} contains an invalid hostname.")
        if host not in result:
            result.append(host)
    return tuple(result)


@dataclass(frozen=True)
class SearchRequest:
    query: str
    max_results: int = 5
    provider: str = "auto"
    time_range: str | None = None
    include_domains: tuple[str, ...] = ()
    exclude_domains: tuple[str, ...] = ()

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> SearchRequest:
        allowed = {
            "query",
            "max_results",
            "provider",
            "time_range",
            "include_domains",
            "exclude_domains",
        }
        if args.keys() - allowed:
            raise WebToolError("invalid_arguments", "Unknown search parameter.")
        query = args.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 400:
            raise WebToolError("invalid_arguments", "query must contain 1 to 400 characters.")
        if any(ord(c) < 32 for c in query) or len(query.split()) > 75:
            raise WebToolError(
                "invalid_arguments", "query must be a single line of at most 75 words."
            )
        provider = args.get("provider", "auto")
        if not isinstance(provider, str) or provider not in (*PROVIDERS, "auto"):
            raise WebToolError("invalid_arguments", "Unknown search provider.")
        time_range = args.get("time_range")
        if time_range is not None and (
            not isinstance(time_range, str) or time_range not in TIME_RANGES
        ):
            raise WebToolError("invalid_arguments", "time_range must be day, week, month or year.")
        return cls(
            query=query.strip(),
            max_results=bounded_int(args, "max_results", 5, 1, 20),
            provider=provider,
            time_range=time_range,
            include_domains=domains(args.get("include_domains", []), "include_domains"),
            exclude_domains=domains(args.get("exclude_domains", []), "exclude_domains"),
        )

    def accepts_url(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")

        def matches(domain: str) -> bool:
            return host == domain or host.endswith("." + domain)

        return (
            not self.include_domains or any(matches(d) for d in self.include_domains)
        ) and not any(matches(d) for d in self.exclude_domains)


@dataclass(frozen=True)
class FetchRequest:
    url: str
    max_chars: int = 8000
    offset: int = 0
    refresh: bool = False

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> FetchRequest:
        if args.keys() - {"url", "max_chars", "offset", "refresh"}:
            raise WebToolError("invalid_arguments", "Unknown fetch parameter.")
        url = args.get("url")
        if not isinstance(url, str) or not url or len(url) > 2048:
            raise WebToolError("invalid_arguments", "url must contain 1 to 2048 characters.")
        if type(args.get("refresh", False)) is not bool:
            raise WebToolError("invalid_arguments", "refresh must be a boolean.")
        return cls(
            url=url,
            max_chars=bounded_int(args, "max_chars", 8000, 100, 12000),
            offset=bounded_int(args, "offset", 0, 0, 2_000_000),
            refresh=args.get("refresh", False),
        )


@dataclass(frozen=True)
class ReadRequest:
    snapshot_id: str
    offset: int = 0
    max_chars: int = 8000

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> ReadRequest:
        if args.keys() - {"snapshot_id", "offset", "max_chars"}:
            raise WebToolError("invalid_arguments", "Unknown snapshot-read parameter.")
        key = args.get("snapshot_id")
        if not isinstance(key, str) or not re.fullmatch(r"snap-[A-Za-z0-9_-]{24}", key):
            raise WebToolError("invalid_arguments", "Use the snapshot_id returned by web_fetch.")
        return cls(
            key,
            bounded_int(args, "offset", 0, 0, 2_000_000),
            bounded_int(args, "max_chars", 8000, 100, 12000),
        )


@dataclass(frozen=True)
class FindRequest:
    snapshot_id: str
    query: str
    case_sensitive: bool = False
    max_matches: int = 10
    context_chars: int = 160

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> FindRequest:
        if args.keys() - {"snapshot_id", "query", "case_sensitive", "max_matches", "context_chars"}:
            raise WebToolError("invalid_arguments", "Unknown snapshot-find parameter.")
        key = ReadRequest.from_args({"snapshot_id": args.get("snapshot_id")}).snapshot_id
        query = args.get("query")
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > 200
            or any(ord(c) < 32 for c in query)
        ):
            raise WebToolError(
                "invalid_arguments", "query must contain 1 to 200 single-line characters."
            )
        if type(args.get("case_sensitive", False)) is not bool:
            raise WebToolError("invalid_arguments", "case_sensitive must be a boolean.")
        return cls(
            key,
            query,
            args.get("case_sensitive", False),
            bounded_int(args, "max_matches", 10, 1, 20),
            bounded_int(args, "context_chars", 160, 0, 500),
        )


def search_requests(args: dict[str, Any]) -> list[SearchRequest]:
    if "queries" not in args:
        return [SearchRequest.from_args(args)]
    if "query" in args:
        raise WebToolError("invalid_arguments", "Supply query or queries, not both.")
    values = args["queries"]
    if not isinstance(values, list) or not 1 <= len(values) <= 5:
        raise WebToolError("invalid_arguments", "queries must contain 1 to 5 queries.")
    common = {k: v for k, v in args.items() if k != "queries"}
    return [SearchRequest.from_args({**common, "query": value}) for value in values]


def fetch_requests(args: dict[str, Any]) -> list[FetchRequest]:
    if "urls" not in args:
        return [FetchRequest.from_args(args)]
    if "url" in args:
        raise WebToolError("invalid_arguments", "Supply url or urls, not both.")
    values = args["urls"]
    if not isinstance(values, list) or not 1 <= len(values) <= 5:
        raise WebToolError("invalid_arguments", "urls must contain 1 to 5 URLs.")
    common = {k: v for k, v in args.items() if k != "urls"}
    return [FetchRequest.from_args({**common, "url": value}) for value in values]


@dataclass(frozen=True)
class SearchResult:
    source_id: str
    title: str
    url: str
    snippet: str
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
