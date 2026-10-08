"""Deterministic documents for an opt-in real-model interface experiment.

HTTP is a fixture here, not a live provider or a network-policy test. Answers
are beyond the initial fetch preview and differ by seed. Importing does no I/O.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ORIGIN = "https://webtool-eval.example"
SEARCH_ENDPOINT = "http://127.0.0.1:31337/search"
CASE_IDS = (
    "single_fact",
    "two_sections",
    "section_read",
    "compare_pages",
    "unicode",
    "count_matches",
    "absent_key",
    "refresh_history",
)


@dataclass(frozen=True)
class Case:
    name: str
    prompt: str
    expected: dict[str, str]
    documents: dict[str, tuple[str, ...]]
    evidence_literals: tuple[str, ...]
    absent_query: str = ""

    @property
    def urls(self) -> list[str]:
        return list(self.documents)


def padding(label: str, count: int = 135) -> str:
    return "\n".join(
        f"Background {label}.{i:03}: This archive records operational context; "
        "the configuration values are specified in dedicated sections."
        for i in range(count)
    )


def document(title: str, *sections: str) -> str:
    parts = [f"# {title}\n\nControlled documentation archive.\n", padding("intro")]
    for i, section in enumerate(sections):
        parts.extend([section, padding(f"appendix-{i}")])
    return "\n\n".join(parts)


def make_case(name: str, seed: int) -> Case:
    rng = random.Random(seed)
    url = f"{ORIGIN}/{name}.txt"
    value = str(rng.randint(31, 89))
    other = str(rng.randint(101, 199))
    docs: dict[str, tuple[str, ...]]
    absent = ""
    if name == "single_fact":
        literal = f"retention_days = {value}"
        docs = {url: (document("Orion retention manual", f"## Retention policy\n{literal}"),)}
        prompt = "Find the Orion retention manual through web search. What is retention_days?"
        expected, literals = {"retention_days": value}, (literal,)
    elif name == "two_sections":
        a, b = f"retry_delay_seconds = {value}", f"queue_capacity = {other}"
        docs = {
            url: (
                document("Orion worker manual", f"## Retry policy\n{a}", f"## Queue policy\n{b}"),
            )
        }
        prompt = f"{url} 문서에서 retry_delay_seconds와 queue_capacity를 각각 확인해주세요."
        expected, literals = {"retry_delay_seconds": value, "queue_capacity": other}, (a, b)
    elif name == "section_read":
        expected = {f"region_{i}_limit": str(rng.randint(201, 999)) for i in range(7)}
        literals = tuple(f"{key} = {val}" for key, val in expected.items())
        section = "## Deployment limits\n" + "\n".join(
            literal
            + "\n"
            + (
                "This limit applies to the named region and preserves its independent operational contract. "
                * 3
            )
            for literal in literals
        )
        docs = {url: (document("Orion deployment manual", section),)}
        prompt = f"In {url}, report all seven region_0_limit through region_6_limit values in the Deployment limits section."
    elif name == "compare_pages":
        second = f"{ORIGIN}/compare_secondary.txt"
        a, b = f"connection_timeout_seconds = {value}", f"connection_timeout_seconds = {other}"
        docs = {
            url: (document("Orion primary region", a),),
            second: (document("Orion secondary region", b),),
        }
        prompt = f"Compare connection_timeout_seconds in {url} and {second}. Return primary_timeout and secondary_timeout."
        expected, literals = {"primary_timeout": value, "secondary_timeout": other}, (a, b)
    elif name == "unicode":
        label = f"서울-{value}-東京"
        literal = f"표시_이름 = {label}"
        docs = {url: (document("국제화 설정 안내", "## 국제화 설정\n" + literal),)}
        prompt = (
            f"{url}에서 표시_이름의 값을 원문 그대로 확인해주세요. 반환 키는 display_name입니다."
        )
        expected, literals = {"display_name": label}, (literal,)
    elif name == "count_matches":
        count = rng.randint(6, 9)
        sections = tuple(
            f"## Handoff record {i}\nHANDOFF_NOTE: archive record {i}" for i in range(count)
        )
        docs = {url: (document("Orion handoff archive", *sections),)}
        prompt = f"{url} 전체 문서에 정확한 문자열 HANDOFF_NOTE가 몇 번 등장하나요? 반환 키는 handoff_count입니다."
        expected, literals = {"handoff_count": str(count)}, ()
    elif name == "absent_key":
        literal = f"rainbow_cache_mode = adaptive-{value}"
        docs = {url: (document("Orion cache settings", literal),)}
        prompt = f"Check {url}: does the exact key enable_rainbow_cache occur? Return legacy_key as present or absent, and the rainbow_cache_mode value."
        expected, literals, absent = (
            {"legacy_key": "absent", "rainbow_cache_mode": f"adaptive-{value}"},
            (literal,),
            "enable_rainbow_cache",
        )
    elif name == "refresh_history":
        a, b = f"rollout_mode = canary-{value}", f"rollout_mode = stable-{other}"
        docs = {url: (document("Orion release status", a), document("Orion release status", b))}
        prompt = (
            f"Capture {url}, then explicitly download a fresh version of the same page. "
            "Revisit the original captured document after refreshing. Report old_mode and new_mode "
            "from those two distinct captures. The archive advances on a fresh download, not on a cached read."
        )
        expected, literals = {"old_mode": f"canary-{value}", "new_mode": f"stable-{other}"}, (a, b)
    else:
        raise ValueError(f"Unknown case: {name}")
    return Case(name, prompt, expected, docs, literals, absent)


class FixtureHTTP:
    """Only returns this case's fixed pages; never opens a connection."""

    timeout = 25.0

    def __init__(self, case: Case, trace: Path | None = None) -> None:
        self.case, self.trace = case, trace
        self.downloads: dict[str, int] = {}
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, url: str, **kwargs: Any):
        from aelix_webtool.errors import WebToolError
        from aelix_webtool.network import HttpResponse

        if method != "GET":
            raise WebToolError("invalid_arguments", "The evaluation archive only supports GET.")
        if url == SEARCH_ENDPOINT:
            data = {
                "results": [
                    {
                        "url": source,
                        "title": text[0].splitlines()[0].removeprefix("# "),
                        "content": "Controlled documentation archive; fetch the source to inspect its settings.",
                    }
                    for source, text in self.case.documents.items()
                ]
            }
            body, mime = json.dumps(data).encode(), "application/json"
            event: dict[str, Any] = {"method": method, "url": url, "kind": "search"}
        elif url in self.case.documents:
            versions = self.case.documents[url]
            number = self.downloads.get(url, 0)
            self.downloads[url] = number + 1
            body, mime = versions[min(number, len(versions) - 1)].encode(), "text/plain"
            event = {
                "method": method,
                "url": url,
                "kind": "fetch",
                "download": number + 1,
                "body_hash": hashlib.sha256(body).hexdigest(),
            }
        else:
            raise WebToolError(
                "network_error", "This URL is outside the controlled evaluation archive."
            )
        self.calls.append(event)
        if self.trace is not None:
            with self.trace.open("a") as stream:
                stream.write(json.dumps(event) + "\n")
        return HttpResponse(url, 200, mime, "utf-8", body)
