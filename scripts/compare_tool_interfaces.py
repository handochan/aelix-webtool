"""Opt-in paired real-model comparison of four versus three web tools.

Uses the same installed wheel, host and deterministic HTTP fixture in both
arms. Credentials live only in a temporary private agent directory. Raw model
events stay in the supplied private output directory. No public API is changed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import shutil
import statistics
import tempfile
import time
from collections import Counter
from importlib.metadata import distribution, version
from pathlib import Path
from typing import Any

from tool_interface_adapter import fixture_module, setup

FIXTURES = fixture_module()
ADAPTER = Path(__file__).with_name("tool_interface_adapter.py")
ROOT = Path(__file__).resolve().parent.parent


def text_content(message: dict[str, Any]) -> str:
    return "\n".join(
        c.get("text", "") for c in message.get("content", []) if c.get("type") == "text"
    )


def final_json(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    texts = [
        text_content(e["message"])
        for e in events
        if e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant"
    ]
    final = next((text for text in reversed(texts) if text.strip()), "")
    try:
        start = final.index("{")
        value, _ = json.JSONDecoder().raw_decode(final[start:])
        return value if isinstance(value, dict) else None
    except (ValueError, json.JSONDecodeError):
        return None


def score(
    case: Any, events: list[dict[str, Any]], http: list[dict[str, Any]], exit_code: int
) -> dict[str, Any]:
    ends = [e for e in events if e.get("type") == "tool_execution_end"]
    successful = [
        e
        for e in ends
        if not (e.get("is_error") or e.get("isError") or e.get("result", {}).get("is_error"))
    ]
    details = [e.get("result", {}).get("details") or {} for e in successful]
    rendered = "\n".join(text_content(e.get("result", {})) for e in successful)
    answer = final_json(events)
    reasons = []
    if exit_code != 0:
        reasons.append("process_error")
    if answer is None:
        reasons.append("missing_json_answer")
    else:
        values = answer.get("answers", {})
        if not isinstance(values, dict) or any(
            str(values.get(k, "")).strip() != v for k, v in case.expected.items()
        ):
            reasons.append("incorrect_values")
        sources = answer.get("sources", [])
        if not isinstance(sources, list) or set(sources) != set(case.urls):
            reasons.append("incorrect_sources")
    if not successful or any(literal not in rendered for literal in case.evidence_literals):
        reasons.append("unobserved_evidence")
    if case.name == "count_matches" and not any(
        d.get("kind") == "find" and d.get("total_matches") == int(case.expected["handoff_count"])
        for d in details
    ):
        reasons.append("count_without_evidence")
    if case.absent_query:
        absent = any(
            d.get("kind") == "find"
            and d.get("query", "").casefold() == case.absent_query.casefold()
            and d.get("total_matches") == 0
            for d in details
        )
        spans = sorted(
            (d.get("offset", 0), d.get("offset", 0) + d.get("returned_chars", 0))
            for d in details
            if d.get("url") == case.urls[0] and d.get("kind") in {"read", "fetch"}
        )
        covered = 0
        for start, end in spans:
            if start > covered:
                break
            covered = max(covered, end)
        if not absent and covered < len(case.documents[case.urls[0]][0].strip()):
            reasons.append("absence_without_evidence")
    fetches = [h for h in http if h.get("kind") == "fetch"]
    if case.name == "refresh_history":
        hashes = {d.get("content_hash") for d in details if d.get("kind") in {"read", "find"}}
        if len(fetches) != 2 or len(hashes - {None}) < 2:
            reasons.append("refresh_or_history_not_verified")
        captured = [
            (i, e.get("result", {}).get("details") or {})
            for i, e in enumerate(successful)
            if (e.get("result", {}).get("details") or {}).get("kind") == "fetch"
        ]
        if len(captured) != 2 or not any(
            i > captured[1][0]
            and d.get("kind") in {"read", "find"}
            and d.get("snapshot_id") == captured[0][1].get("snapshot_id")
            for i, d in enumerate(details)
        ):
            reasons.append("old_snapshot_not_revisited_after_refresh")
    errors = []
    for event in ends:
        result = event.get("result", {})
        if event.get("is_error") or event.get("isError") or result.get("is_error"):
            code = (result.get("details") or {}).get("error", {}).get("code", "")
            content = text_content(result).lower()
            if not code and any(
                word in content
                for word in (
                    "validation",
                    "invalid argument",
                    "unknown parameter",
                    "additional properties",
                )
            ):
                code = "invalid_arguments"
            errors.append(
                {
                    "tool": event.get("tool_name", event.get("toolName")),
                    "code": code or "tool_error",
                }
            )
    assistants = [
        e["message"]
        for e in events
        if e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant"
    ]
    usage = [m["usage"] for m in assistants if isinstance(m.get("usage"), dict)]
    tokens = {
        field: sum(u.get(field, 0) or 0 for u in usage)
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read",
            "cache_write",
            "reasoning",
            "total_tokens",
        )
    }
    # This host reports input_tokens excluding cache hits. reasoning is already
    # inside output_tokens; total_tokens includes cached input exactly once.
    tokens["logical_input_tokens"] = (
        tokens["input_tokens"] + tokens["cache_read"] + tokens["cache_write"]
    )
    usage_consistent = all(
        u.get("total_tokens", 0)
        == u.get("input_tokens", 0)
        + u.get("cache_read", 0)
        + u.get("cache_write", 0)
        + u.get("output_tokens", 0)
        for u in usage
    )
    return {
        "success": not reasons,
        "failure_reasons": reasons,
        "answer": answer,
        "tool_calls": len(ends),
        "tool_errors": len(errors),
        "errors": errors,
        "invalid_arguments": sum(e["code"] == "invalid_arguments" for e in errors),
        "tool_names": dict(Counter(e.get("tool_name", e.get("toolName")) for e in ends)),
        "operations": dict(Counter(d.get("kind", "unknown") for d in details)),
        "http_downloads": len(fetches),
        "fixture_searches": sum(h.get("kind") == "search" for h in http),
        "model_responses": len(assistants),
        "usage_responses": len(usage),
        "usage_consistent": usage_consistent,
        "tokens": tokens,
        "first_usage": usage[0] if usage else {},
    }


async def definitions() -> dict[str, Any]:
    from aelix_coding_agent.extensions.loader import load_extensions

    old = os.environ.get("AELIX_WEB_EVAL_ARM")
    result = {}
    try:
        for arm in ("four", "three"):
            os.environ["AELIX_WEB_EVAL_ARM"] = arm
            loaded = await load_extensions([setup])
            assert not loaded.errors, [(e.path, e.error) for e in loaded.errors]
            tools = list(loaded.extensions[0].tools.values())
            assert len(tools) == (4 if arm == "four" else 3)
            serial = [
                {"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in tools
            ]
            canonical = json.dumps(
                serial, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
            result[arm] = {
                "tools": serial,
                "json_bytes": len(canonical.encode()),
                "json_chars": len(canonical),
                "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            }
    finally:
        if old is None:
            os.environ.pop("AELIX_WEB_EVAL_ARM", None)
        else:
            os.environ["AELIX_WEB_EVAL_ARM"] = old
    return result


async def trial(
    args: argparse.Namespace, agent: Path, arm: str, case_name: str, seed: int, repeat: int
) -> dict[str, Any]:
    case = FIXTURES.make_case(case_name, seed)
    out = args.output / f"r{repeat}-{case_name}-{arm}"
    out.mkdir(mode=0o700)
    env = os.environ.copy()
    for name in (
        "BRAVE_API_KEY",
        "TAVILY_API_KEY",
        "EXA_API_KEY",
        "AELIX_WEB_SEARXNG_URL",
        "AELIX_WEB_OFFLINE",
        "AELIX_WEB_RETRIES",
        "AELIX_WEB_FALLBACK_PROVIDERS",
    ):
        env.pop(name, None)
    env.update(
        {
            "AELIX_CODING_AGENT_DIR": str(agent),
            "AELIX_DEFAULT_CATALOG": "",
            "AELIX_WEB_PROVIDER": "searxng",
            "AELIX_WEB_EVAL_FIXTURE": "1",
            "AELIX_WEB_EVAL_ARM": arm,
            "AELIX_WEB_EVAL_CASE": case_name,
            "AELIX_WEB_EVAL_SEED": str(seed),
            "AELIX_WEB_EVAL_TRACE": str(out / "http.jsonl"),
        }
    )
    prompt = (
        "Use the available web tools to investigate the controlled documentation archive. "
        "Return one JSON object with answers (all requested values as strings) and sources "
        "(the exact source document URLs). Base answers on retrieved evidence, not guesses. "
        "Prefer relevant passages to paging through irrelevant text.\n\n" + case.prompt
    )
    command = [
        str(args.aelix.resolve()),
        "--provider",
        args.provider,
        "--model",
        args.model,
        "--thinking",
        args.thinking,
        "--mode",
        "json",
        "--no-session",
        "--no-skills",
        "--no-agents",
        "--no-context-files",
        "--offline",
        "--no-extensions",
        "-e",
        str(ADAPTER),
        "--tools",
        "web_search,web_fetch,web_read,web_find"
        if arm == "four"
        else "web_search,web_fetch,web_read",
        "-p",
        prompt,
    ]
    began = time.perf_counter()
    process = await asyncio.create_subprocess_exec(
        *command, cwd=out, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert process.stdout is not None and process.stderr is not None
    events: list[dict[str, Any]] = []
    limit = ""

    async def consume() -> None:
        nonlocal limit
        ends = 0
        with (
            (out / "events.jsonl").open("wb") as raw,
            (out / "timed-events.jsonl").open("w") as timed,
        ):
            async for line in process.stdout:
                raw.write(line)
                raw.flush()
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                events.append(event)
                timed.write(
                    json.dumps(
                        {"elapsed": time.perf_counter() - began, "event": event}, ensure_ascii=False
                    )
                    + "\n"
                )
                if event.get("type") == "tool_execution_end":
                    ends += 1
                    if ends > args.max_calls and process.returncode is None:
                        limit = "tool_call_limit"
                        process.kill()

    consumer = asyncio.create_task(consume())
    stderr_task = asyncio.create_task(process.stderr.read())
    try:
        await asyncio.wait_for(process.wait(), args.timeout)
    except TimeoutError:
        limit = "deadline"
        if process.returncode is None:
            process.kill()
        await process.wait()
    finally:
        await consumer
    stderr = await stderr_task
    (out / "stderr.txt").write_bytes(stderr)
    http_file = out / "http.jsonl"
    http = (
        [json.loads(line) for line in http_file.read_text().splitlines()]
        if http_file.exists()
        else []
    )
    assert process.returncode is not None
    result = score(case, events, http, process.returncode)
    result.update(
        arm=arm,
        case=case_name,
        seed=seed,
        repeat=repeat,
        wall_seconds=time.perf_counter() - began,
        exit_code=process.returncode,
        limit=limit,
        stderr_bytes=len(stderr),
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
    )
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "arm",
                    "case",
                    "repeat",
                    "success",
                    "failure_reasons",
                    "tool_calls",
                    "invalid_arguments",
                    "wall_seconds",
                )
            }
        ),
        flush=True,
    )
    return result


def aggregate(rows: list[dict[str, Any]], defs: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"arms": {}, "pairs": {}}
    for arm in ("four", "three"):
        selected = [r for r in rows if r["arm"] == arm]
        result["arms"][arm] = {
            "trials": len(selected),
            "successes": sum(r["success"] for r in selected),
            "tool_errors": sum(r["tool_errors"] for r in selected),
            "invalid_arguments": sum(r["invalid_arguments"] for r in selected),
            "median_tool_calls": statistics.median(r["tool_calls"] for r in selected),
            "median_wall_seconds": statistics.median(r["wall_seconds"] for r in selected),
            "median_reported_tokens": statistics.median(
                r["tokens"]["total_tokens"] for r in selected
            ),
            "total_reported_tokens": sum(r["tokens"]["total_tokens"] for r in selected),
            "total_cache_read": sum(r["tokens"]["cache_read"] for r in selected),
            "definitions_json_bytes": defs[arm]["json_bytes"],
        }
    pairs: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        pairs.setdefault((row["case"], row["repeat"]), {})[row["arm"]] = row
    discordant = Counter()
    differences: dict[str, list[float]] = {
        "wall_seconds": [],
        "tool_calls": [],
        "reported_tokens": [],
    }
    for pair in pairs.values():
        assert set(pair) == {"three", "four"}
        a, b = pair["four"], pair["three"]
        assert a["prompt_sha256"] == b["prompt_sha256"] and a["seed"] == b["seed"]
        discordant[f"four_{int(a['success'])}_three_{int(b['success'])}"] += 1
        differences["wall_seconds"].append(b["wall_seconds"] - a["wall_seconds"])
        differences["tool_calls"].append(b["tool_calls"] - a["tool_calls"])
        differences["reported_tokens"].append(
            b["tokens"]["total_tokens"] - a["tokens"]["total_tokens"]
        )
    wins, losses = discordant["four_0_three_1"], discordant["four_1_three_0"]
    n = wins + losses
    p = (
        min(1.0, 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2**n)
        if n
        else 1.0
    )
    result["pairs"] = {
        "count": len(pairs),
        "outcomes": dict(discordant),
        "discordant_exact_p": p,
        "median_three_minus_four": {k: statistics.median(v) for k, v in differences.items()},
    }
    return result


async def run(args: argparse.Namespace) -> None:
    args.output = args.output.resolve()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Use a new empty output directory; preserve previous trial evidence.")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=True)
    auth = args.auth_file.expanduser()
    if not auth.is_file():
        raise SystemExit("Configured model auth is required for this opt-in experiment.")
    defs = await definitions()
    (args.output / "definitions.json").write_text(
        json.dumps(defs, ensure_ascii=False, indent=2) + "\n"
    )
    direct = json.loads(distribution("aelix-webtool").read_text("direct_url.json") or "{}")
    metadata = {
        "provider": args.provider,
        "model": args.model,
        "thinking": args.thinking,
        "repeats": args.repeats,
        "cases": args.cases,
        "seed": args.seed,
        "timeout": args.timeout,
        "max_calls": args.max_calls,
        "network": "deterministic HTTP fixture, no live web provider",
        "extension_version": version("aelix-webtool"),
        "extension_source": direct,
        "host_versions": {
            name: version(name) for name in ("aelix-ai", "aelix-agent-core", "aelix-coding-agent")
        },
        "script_hashes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                ADAPTER,
                Path(__file__).with_name("tool_interface_fixture.py"),
            )
        },
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rows = []
    rng = random.Random(args.seed)
    with tempfile.TemporaryDirectory(prefix="webtool-interface-auth-") as directory:
        agent = Path(directory)
        agent.chmod(0o700)
        shutil.copy2(auth, agent / "auth.json")
        (agent / "auth.json").chmod(0o600)
        for repeat in range(args.repeats):
            cases = list(args.cases)
            rng.shuffle(cases)
            for case_name in cases:
                seed = args.seed + repeat * 100 + FIXTURES.CASE_IDS.index(case_name)
                arms = ["four", "three"]
                rng.shuffle(arms)
                for arm in arms:
                    rows.append(await trial(args, agent, arm, case_name, seed, repeat))
                    (args.output / "results.json").write_text(
                        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
                    )
    summary = aggregate(rows, defs)
    summary["metadata"] = metadata
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aelix", type=Path, required=True)
    parser.add_argument("--provider", default="openai-codex")
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--thinking", default="low")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--cases", nargs="+", choices=FIXTURES.CASE_IDS, default=list(FIXTURES.CASE_IDS)
    )
    parser.add_argument("--seed", type=int, default=271828)
    parser.add_argument("--timeout", type=float, default=150)
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--auth-file", type=Path, default=Path.home() / ".aelix/agent/auth.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5 or not 1 <= args.max_calls <= 20 or not 10 <= args.timeout <= 300:
        parser.error("Use 1-5 repeats, 1-20 calls and a 10-300 second deadline")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
