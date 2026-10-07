"""Generate a candidate for a reviewed, published 40-hex git revision."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument(
        "--base", type=Path, help="Current marketplace catalog.json; preserve its other entries"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("revision must be a full lowercase 40-hex commit SHA")
    document = (
        json.loads(args.base.read_text())
        if args.base
        else {
            "schemaVersion": 1,
            "name": "Aelix official catalog",
            "extensions": [],
        }
    )
    entries = document.get("extensions")
    if not isinstance(entries, list):
        parser.error("base catalog must contain an extensions array")
    if any(e.get("name") == "aelix-webtool" for e in entries if isinstance(e, dict)):
        parser.error("the base catalog already lists aelix-webtool; update that entry explicitly")
    entries.append(
        {
            "name": "aelix-webtool",
            "source": f"git+https://github.com/handochan/aelix-webtool.git@{args.revision}",
            "description": "Keyless DuckDuckGo or configured Brave, Tavily, Exa or SearXNG search, and bounded public-page reading.",
            "version": "0.1.0",
            "homepage": "https://github.com/handochan/aelix-webtool",
        }
    )
    document["updated"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    print(
        f"Wrote candidate {args.output}. This does not publish the source or register the extension."
    )


if __name__ == "__main__":
    main()
