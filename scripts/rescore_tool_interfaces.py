"""Supplement original strict JSON-shape scores with format-tolerant task scores.

Does not overwrite original scores or rerun/change trials. Accepts flat or
nested answers and equivalent URL list/map/string citation forms. Incorrect
facts, unobserved evidence, absence/count/refresh failures still fail.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
from pathlib import Path
from typing import Any

from compare_tool_interfaces import FIXTURES, aggregate, score


def functional_score(
    case: Any, events: list[dict[str, Any]], http: list[dict[str, Any]], code: int
) -> dict[str, Any]:
    result = score(case, events, http, code)
    result["strict_success"] = result["success"]
    answer = result["answer"]
    result["shape_compliant"] = (
        isinstance(answer, dict)
        and isinstance(answer.get("answers"), dict)
        and isinstance(answer.get("sources"), list)
    )
    if isinstance(answer, dict):
        values = answer.get("answers", answer)
        if isinstance(values, dict) and all(
            str(values.get(k, "")).strip() == val for k, val in case.expected.items()
        ):
            result["failure_reasons"] = [
                r for r in result["failure_reasons"] if r != "incorrect_values"
            ]
        sources = answer.get("sources")
        if isinstance(sources, str):
            sources = [sources]
        elif isinstance(sources, dict):
            sources = list(sources.values())
        if (
            isinstance(sources, list)
            and all(isinstance(s, str) for s in sources)
            and set(sources) == set(case.urls)
        ):
            result["failure_reasons"] = [
                r for r in result["failure_reasons"] if r != "incorrect_sources"
            ]
    result["success"] = not result["failure_reasons"]
    return result


def rescore(directory: Path) -> dict[str, Any]:
    original = json.loads((directory / "results.json").read_text())
    defs = json.loads((directory / "definitions.json").read_text())
    metadata = json.loads((directory / "metadata.json").read_text())
    rows = []
    for row in original:
        out = directory / f"r{row['repeat']}-{row['case']}-{row['arm']}"
        events = []
        for line in (out / "events.jsonl").read_text().splitlines():
            with contextlib.suppress(ValueError):
                events.append(json.loads(line))
        path = out / "http.jsonl"
        http = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        updated = functional_score(
            FIXTURES.make_case(row["case"], row["seed"]), events, http, row["exit_code"]
        )
        rows.append({**row, **updated})
    summary = aggregate(rows, defs)
    summary["metadata"] = metadata
    summary["scoring"] = {
        "original_strict_summary": "summary.json",
        "functional_definition": "same required named values; flat/nested answers and list/map/string URL citations accepted; original source-evidence requirements retained",
        "posthoc_format_assessment": True,
        "rescorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "strict_successes": {
            arm: sum(r["strict_success"] for r in rows if r["arm"] == arm)
            for arm in ("four", "three")
        },
        "shape_compliant": {
            arm: sum(r["shape_compliant"] for r in rows if r["arm"] == arm)
            for arm in ("four", "three")
        },
        "usage_complete": all(
            r["model_responses"] == r["usage_responses"] and r["usage_consistent"] for r in rows
        ),
    }
    (directory / "functional-results.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    )
    (directory / "functional-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args()
    for directory in args.directories:
        print(json.dumps({"directory": str(directory), "summary": rescore(directory)}, indent=2))


if __name__ == "__main__":
    main()
