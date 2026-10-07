"""Opt-in real-model E2E: fixture or keyless live search -> public fetch -> answer.

This sends a small prompt to the configured Aelix model. The default uses a
local SearXNG fixture; --search-provider duckduckgo performs a live keyless search.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent


async def run(args: argparse.Namespace) -> None:
    hits: list[dict[str, str]] = []
    use_fixture = args.search_provider == "searxng"

    async def search(request: web.Request) -> web.Response:
        hits.append({"q": request.query.get("q", ""), "format": request.query.get("format", "")})
        return web.json_response(
            {
                "results": [
                    {
                        "title": "Python asyncio official documentation",
                        "url": "https://docs.python.org/3/library/asyncio.html",
                        "content": "AELIX_WEBTOOL_E2E_SOURCE_20261008: asyncio provides concurrent Python code using async/await.",
                    }
                ]
            }
        )

    runner = None
    port = 0
    if use_fixture:
        app = web.Application()
        app.router.add_get("/search", search)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        assert site._server is not None
        port = site._server.sockets[0].getsockname()[1]
    try:
        with tempfile.TemporaryDirectory(prefix="webtool-model-e2e-") as temp:
            root = Path(temp)
            agent = root / "agent"
            agent.mkdir(mode=0o700)
            auth = args.auth_file.expanduser()
            if not auth.is_file():
                raise SystemExit(
                    "No configured Aelix auth file; pass --auth-file or authenticate first."
                )
            # A private temporary copy isolates globals/settings/sessions.
            # The original credentials are untouched and the copy is removed.
            shutil.copy2(auth, agent / "auth.json")
            (agent / "auth.json").chmod(0o600)
            env = os.environ.copy()
            env.update(
                {
                    "AELIX_CODING_AGENT_DIR": str(agent),
                    "AELIX_DEFAULT_CATALOG": "",
                    "AELIX_WEB_PROVIDER": args.search_provider,
                }
            )
            env.pop("AELIX_WEB_OFFLINE", None)
            for name in ("BRAVE_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY", "AELIX_WEB_SEARXNG_URL"):
                env.pop(name, None)
            if use_fixture:
                env["AELIX_WEB_SEARXNG_URL"] = f"http://127.0.0.1:{port}"
            prompt = (
                (
                    "Integration check: use only web_search and web_fetch. First call web_search "
                    "with query 'AELIX_WEBTOOL_E2E_SOURCE_20261008 Python asyncio'. Then call "
                    "web_fetch on the returned official documentation URL. Finally report the exact "
                    "fixture source marker and one fact verified from the fetched page, citing its URL. "
                    "You must call both tools; do not answer from prior knowledge."
                )
                if use_fixture
                else (
                    "Integration check: use only web_search and web_fetch. Make exactly one "
                    "web_search call with query 'Python asyncio official documentation'. "
                    "Then use web_fetch on its returned official docs.python.org asyncio page. "
                    "Finally state one fact verified from the page and cite its URL. "
                    "You must call both tools. If search is blocked, stop and report the error; "
                    "do not retry or use another provider."
                )
            )
            command = [
                str(args.aelix.resolve()),
                "--provider",
                args.provider,
                "--model",
                args.model,
                "--mode",
                "json",
                "--no-session",
                "--no-skills",
                "--no-agents",
                "--no-context-files",
                "--offline",
                "--tools",
                "web_search,web_fetch",
                "-p",
                prompt,
            ]
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=root,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await process.communicate()
                raise
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "events.jsonl").write_bytes(stdout)
            (args.output / "stderr.txt").write_bytes(stderr)
            events = []
            for line in stdout.decode().splitlines():
                with contextlib.suppress(ValueError):
                    events.append(json.loads(line))
            tool_ends = [e for e in events if e.get("type") == "tool_execution_end"]
            executed = {e.get("toolName") or e.get("tool_name") for e in tool_ends}
            assistant_texts = [
                "\n".join(
                    c.get("text", "")
                    for c in e["message"].get("content", [])
                    if c.get("type") == "text"
                )
                for e in events
                if e.get("type") == "message_end"
                and e.get("message", {}).get("role") == "assistant"
            ]
            final_answer = next((text for text in reversed(assistant_texts) if text), "")
            summary = {
                "exit_code": process.returncode,
                "provider": args.provider,
                "model": args.model,
                "search_provider": args.search_provider,
                "search_source": "local fixture" if use_fixture else "live DuckDuckGo Lite",
                "search_fixture_requests": hits,
                "executed_tools": sorted(executed),
                "tool_end_events": tool_ends,
                "final_answer": final_answer,
            }
            (args.output / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
            )
            print(
                json.dumps(
                    {k: v for k, v in summary.items() if k != "tool_end_events"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if (
                process.returncode != 0
                or not {"web_search", "web_fetch"} <= executed
                or (use_fixture and not hits)
            ):
                raise SystemExit(
                    "FAIL: inspect saved E2E events; both tools were not successfully dispatched."
                )
            if any(
                e.get("isError") or e.get("is_error") or e.get("result", {}).get("is_error")
                for e in tool_ends
            ):
                raise SystemExit(
                    "FAIL: a tool execution returned an error; inspect saved E2E events."
                )
            if (
                use_fixture and "AELIX_WEBTOOL_E2E_SOURCE_20261008" not in final_answer
            ) or "https://docs.python.org/3/library/asyncio.html" not in final_answer:
                raise SystemExit("FAIL: final answer omitted the required evidence or source URL.")
            print(f"PASS: real-model search -> fetch -> response ({summary['search_source']})")
    finally:
        if runner is not None:
            await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aelix", type=Path, default=ROOT / ".venv/bin/aelix")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--search-provider", choices=["searxng", "duckduckgo"], default="searxng")
    parser.add_argument("--auth-file", type=Path, default=Path.home() / ".aelix/agent/auth.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".devstate/model-e2e")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
