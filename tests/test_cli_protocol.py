from __future__ import annotations

import asyncio
import json
import os
import sys

from aiohttp import web


async def test_cli_all_failed_batch_exits_nonzero_without_echoing_response_body():
    hits = []

    async def handler(request):
        hits.append(request.query.get("q"))
        return web.Response(status=503, text="PRIVATE_UPSTREAM_BODY")

    app = web.Application()
    app.router.add_get("/search", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    env = {
        **os.environ,
        "AELIX_WEB_PROVIDER": "searxng",
        "AELIX_WEB_SEARXNG_URL": f"http://127.0.0.1:{port}",
        "AELIX_WEB_RETRIES": "0",
        "AELIX_WEB_FALLBACK_PROVIDERS": "",
    }
    env.pop("AELIX_WEB_OFFLINE", None)
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "aelix_webtool.cli",
            "search",
            "one",
            "two",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        result = json.loads(stdout)
        assert process.returncode == 1 and result["failed"] == 2 and result["is_error"] is True
        assert sorted(hits) == ["one", "two"]
        assert b"PRIVATE_UPSTREAM_BODY" not in stdout + stderr
    finally:
        await runner.cleanup()
