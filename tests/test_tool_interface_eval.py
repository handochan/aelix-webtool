from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from compare_tool_interfaces import FIXTURES, score  # noqa: E402 - explicit sibling scripts
from rescore_tool_interfaces import functional_score  # noqa: E402
from tool_interface_adapter import setup  # noqa: E402

pytest.importorskip("aelix_coding_agent")
from aelix_ai.tools import ToolExecutionContext, validate_tool_arguments  # noqa: E402
from aelix_coding_agent.extensions.loader import load_extensions  # noqa: E402


@pytest.mark.parametrize("name", FIXTURES.CASE_IDS)
def test_fixture_answers_are_not_in_initial_preview_and_are_seeded(name):
    case = FIXTURES.make_case(name, 41)
    assert case.expected != FIXTURES.make_case(name, 42).expected
    for literal in case.evidence_literals:
        assert all(literal not in versions[0][:8000] for versions in case.documents.values())
        assert any(literal in text for versions in case.documents.values() for text in versions)
    assert all(
        len(text.encode()) < 2_000_000 for versions in case.documents.values() for text in versions
    )


def test_correct_guess_without_retrieved_evidence_is_not_a_success():
    import json

    case = FIXTURES.make_case("single_fact", 41)
    events = [
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"answers": case.expected, "sources": case.urls}),
                    }
                ],
            },
        }
    ]
    result = score(case, events, [], 0)
    assert not result["success"] and "unobserved_evidence" in result["failure_reasons"]


@pytest.mark.parametrize("citation", ["string", "map", "list"])
def test_functional_assessment_preserves_evidence_and_accepts_equivalent_answer_shapes(citation):
    import json

    case = FIXTURES.make_case("single_fact", 41)
    sources = {"string": case.urls[0], "map": {"retention_days": case.urls[0]}, "list": case.urls}[
        citation
    ]
    final = {**case.expected, "sources": sources}
    events = [
        {
            "type": "tool_execution_end",
            "tool_name": "web_read",
            "result": {
                "content": [{"type": "text", "text": case.evidence_literals[0]}],
                "details": {"kind": "find"},
            },
        },
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": json.dumps(final)}],
            },
        },
    ]
    corrected = functional_score(case, events, [], 0)
    assert corrected["success"] and not corrected["strict_success"]
    guessed = functional_score(case, events[1:], [], 0)
    assert not guessed["success"] and "unobserved_evidence" in guessed["failure_reasons"]
    final["retention_days"] = "wrong"
    events[1]["message"]["content"][0]["text"] = json.dumps(final)
    assert not functional_score(case, events, [], 0)["success"]


@pytest.mark.parametrize("arm,count", [("four", 4), ("three", 3)])
async def test_actual_host_interface_and_stored_results(monkeypatch, arm, count):
    monkeypatch.setenv("AELIX_WEB_EVAL_ARM", arm)
    monkeypatch.setenv("AELIX_WEB_EVAL_CASE", "single_fact")
    monkeypatch.setenv("AELIX_WEB_EVAL_SEED", "41")
    monkeypatch.delenv("AELIX_WEB_EVAL_TRACE", raising=False)
    loaded = await load_extensions([setup])
    assert not loaded.errors
    ext = loaded.extensions[0]
    assert len(ext.tools) == count
    ctx = ToolExecutionContext()
    case = FIXTURES.make_case("single_fact", 41)
    fetched = await ext.tools["web_fetch"].execute({"url": case.urls[0]}, ctx)
    assert not fetched.is_error
    key = fetched.details["snapshot_id"]
    name = "web_find" if arm == "four" else "web_read"
    query_key = "query" if arm == "four" else "find_text"
    finder = ext.tools[name]
    args = await validate_tool_arguments(finder, {"snapshot_id": key, query_key: "retention_days"})
    assert "offset" not in args and "max_chars" not in args
    found = await finder.execute(args, ctx)
    assert found.details["total_matches"] == 1
    read = await ext.tools["web_read"].execute(
        {"snapshot_id": key, "offset": found.details["matches"][0]["start"], "max_chars": 300}, ctx
    )
    assert case.evidence_literals[0] in read.content[0].text
    assert read.details["content_hash"] == fetched.details["content_hash"]
    ext.handlers["session_start"][0]({}, None)
    missing = await ext.tools["web_read"].execute({"snapshot_id": key}, ctx)
    assert missing.is_error and missing.details["error"]["code"] == "snapshot_not_found"


@pytest.mark.parametrize(
    "extra",
    [
        {"find_text": "key", "offset": 0},
        {"find_text": "key", "max_chars": 400},
        {"case_sensitive": True},
        {"context_chars": 12},
        {"query": "key"},
        {"find_text": ""},
    ],
)
async def test_combined_host_schema_rejects_mixed_or_ambiguous_arguments(monkeypatch, extra):
    monkeypatch.setenv("AELIX_WEB_EVAL_ARM", "three")
    loaded = await load_extensions([setup])
    assert not loaded.errors
    tool = loaded.extensions[0].tools["web_read"]
    with pytest.raises(Exception) as error:
        await validate_tool_arguments(tool, {"snapshot_id": "snap-" + "a" * 24, **extra})
    assert "valid" in str(error.value).lower() or "argument" in str(error.value).lower()


async def test_combined_execution_keeps_cancellation_and_private_url_policy(monkeypatch):
    import asyncio

    from aelix_coding_agent.tools._abort import AbortSignal

    monkeypatch.setenv("AELIX_WEB_EVAL_ARM", "three")
    ext = (await load_extensions([setup])).extensions[0]
    blocked = await ext.tools["web_fetch"].execute(
        {"url": "http://127.0.0.1/private"}, ToolExecutionContext()
    )
    assert blocked.is_error and blocked.details["error"]["code"] == "blocked_url"
    signal = AbortSignal()
    signal.abort()
    with pytest.raises(asyncio.CancelledError):
        await ext.tools["web_read"].execute(
            {"snapshot_id": "snap-" + "a" * 24, "find_text": "key"},
            ToolExecutionContext(signal=signal),
        )
