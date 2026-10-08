"""Control first-request token measurements with the same working directory.

The main cohort preserved a separate artifact/cwd directory per arm. This
supplement holds cwd constant without modifying its frozen runner or adapters.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

from compare_tool_interfaces import run


async def check(args: argparse.Namespace) -> None:
    original = asyncio.create_subprocess_exec
    with tempfile.TemporaryDirectory(prefix="webtool-common-cwd-") as directory:

        async def same_directory(*command, **kwargs):
            kwargs["cwd"] = directory
            return await original(*command, **kwargs)

        asyncio.create_subprocess_exec = same_directory
        try:
            await run(args)
        finally:
            asyncio.create_subprocess_exec = original
    for filename in ("metadata.json", "summary.json"):
        path = args.output / filename
        data = json.loads(path.read_text())
        meta = data if filename == "metadata.json" else data["metadata"]
        meta["cwd_control"] = "one common empty working directory for both arms"
        meta["control_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        path.write_text(json.dumps(data, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aelix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.provider, args.model, args.thinking = "openai-codex", "gpt-5.6-luna", "low"
    args.repeats, args.cases, args.seed = 1, ["single_fact", "section_read"], 271828
    args.timeout, args.max_calls = 150, 12
    args.auth_file = Path.home() / ".aelix/agent/auth.json"
    asyncio.run(check(args))


if __name__ == "__main__":
    main()
