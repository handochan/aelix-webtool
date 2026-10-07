"""Keyless first-page DuckDuckGo Lite search through the bounded HTTP client."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from yarl import URL

from .errors import WebToolError
from .extract import decode
from .network import HttpResponse, validate_url

SEARCH_URL = "https://lite.duckduckgo.com/lite/"


def blocked() -> WebToolError:
    return WebToolError(
        "provider_blocked",
        "DuckDuckGo blocked the search or requested human verification. "
        "Try again later or choose a configured provider.",
    )


def result_url(href: str) -> str | None:
    try:
        link = URL(urljoin(SEARCH_URL, href))
        if link.host in {"duckduckgo.com", "lite.duckduckgo.com"}:
            if link.path in {"/y.js", "/anomaly.js"}:
                return None
            if link.path.rstrip("/") == "/l":
                destination = link.query.get("uddg")
                if not destination:
                    return None
                return validate_url(destination)
        return validate_url(str(link))
    except (WebToolError, ValueError, UnicodeError):
        return None


def parse_results(response: HttpResponse) -> list[dict[str, Any]]:
    if response.status == 202:
        raise blocked()
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        raise WebToolError("invalid_response", "DuckDuckGo returned an unexpected content type.")
    soup = BeautifulSoup(decode(response), "html.parser")
    if soup.select_one('#challenge-form, .anomaly-modal__modal, form[action*="/anomaly.js"]'):
        raise blocked()
    results: list[dict[str, Any]] = []
    for anchor in soup.select("a.result-link"):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        url = result_url(href)
        title = " ".join(anchor.get_text().split())
        if not url or not title:
            continue
        snippet = ""
        row = anchor.find_parent("tr")
        if row is not None:
            # Snippets are in a following row. Stop at the next result so a
            # missing snippet cannot acquire a different source's evidence.
            for sibling in row.next_siblings:
                if not isinstance(sibling, Tag):
                    continue
                if sibling.select_one("a.result-link"):
                    break
                found = sibling.select_one(".result-snippet")
                if found is not None:
                    snippet = " ".join(found.get_text().split())
                    break
        results.append({"title": title, "url": url, "content": snippet})
    if not results and not soup.select_one(".no-results, .no-results__message"):
        raise WebToolError(
            "invalid_response",
            "DuckDuckGo returned no recognizable result page. Its page format may have changed.",
        )
    return results
