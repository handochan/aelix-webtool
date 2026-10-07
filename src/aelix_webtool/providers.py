"""Small search adapters: one request, no model calls and no fallback chain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from yarl import URL

from .config import Config
from .errors import WebToolError
from .models import SearchRequest
from .network import HttpClient, validate_url


def filtered_query(request: SearchRequest) -> str:
    parts = [request.query]
    if request.include_domains:
        parts.append("(" + " OR ".join("site:" + d for d in request.include_domains) + ")")
    parts.extend("-site:" + d for d in request.exclude_domains)
    return " ".join(parts)


def result_rows(payload: dict[str, Any], *, brave: bool = False) -> list[dict[str, Any]]:
    if brave:
        web = payload.get("web")
        # A successful Brave search can have no web section when no results exist.
        if web is None:
            if payload.get("type") == "search" or isinstance(payload.get("query"), dict):
                return []
            raise WebToolError("invalid_response", "Brave returned an unexpected response shape.")
        if not isinstance(web, dict):
            raise WebToolError("invalid_response", "Brave returned an unexpected web result shape.")
        rows = web.get("results")
    else:
        rows = payload.get("results")
    if not isinstance(rows, list):
        raise WebToolError("invalid_response", "The provider response is missing its results list.")
    return [r for r in rows if isinstance(r, dict)]


async def search_provider(
    provider: str,
    request: SearchRequest,
    config: Config,
    http: HttpClient,
) -> list[dict[str, Any]]:
    if provider == "brave":
        query = filtered_query(request)
        if len(query) > 600 or len(query.split()) > 75:
            raise WebToolError(
                "invalid_arguments",
                "The query including domain filters exceeds Brave's 600-character/75-word limit.",
            )
        params: dict[str, Any] = {
            "q": query,
            "count": request.max_results,
            "result_filter": "web",
            "text_decorations": "false",
            "extra_snippets": "true",
        }
        if request.time_range:
            params["freshness"] = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}[
                request.time_range
            ]
        response = await http.request(
            "GET",
            "https://api.search.brave.com/res/v1/web/search",
            params=params,
            headers={"X-Subscription-Token": config.keys[provider]},
        )
        return result_rows(response.json(), brave=True)

    if provider == "tavily":
        body: dict[str, Any] = {
            "query": request.query,
            "max_results": request.max_results,
            "search_depth": "basic",
            "topic": "general",
            "auto_parameters": False,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_domains": list(request.include_domains),
            "exclude_domains": list(request.exclude_domains),
        }
        if request.time_range:
            body["time_range"] = request.time_range
        response = await http.request(
            "POST",
            "https://api.tavily.com/search",
            json_body=body,
            headers={"Authorization": "Bearer " + config.keys[provider]},
        )
        return result_rows(response.json())

    if provider == "exa":
        body = {
            "query": request.query,
            "numResults": request.max_results,
            "type": "auto",
            "contents": {"highlights": True},
        }
        if request.include_domains:
            body["includeDomains"] = list(request.include_domains)
        if request.exclude_domains:
            body["excludeDomains"] = list(request.exclude_domains)
        if request.time_range:
            days = {"day": 1, "week": 7, "month": 30, "year": 365}[request.time_range]
            body["startPublishedDate"] = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        response = await http.request(
            "POST",
            "https://api.exa.ai/search",
            json_body=body,
            headers={"x-api-key": config.keys[provider]},
        )
        return result_rows(response.json())

    if provider == "searxng":
        if request.time_range == "week":
            raise WebToolError(
                "unsupported_filter",
                "SearXNG supports day, month and year; week is unsupported. Choose another range or provider.",
            )
        validate_url(config.searxng_url, allow_private=True)
        base_url = URL(config.searxng_url)
        if base_url.query or base_url.fragment:
            raise WebToolError(
                "configuration",
                "AELIX_WEB_SEARXNG_URL must be a base URL without query parameters.",
            )
        url = str(base_url.with_path(base_url.path.rstrip("/") + "/search"))
        params = {"q": filtered_query(request), "format": "json", "categories": "general"}
        if request.time_range:
            params["time_range"] = request.time_range
        response = await http.request("GET", url, params=params, allow_private=True)
        return result_rows(response.json())

    raise WebToolError("configuration", "Unknown search provider.")
