"""A model-free CLI for diagnostics and live provider smoke tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .errors import WebToolError
from .models import FindRequest, fetch_requests, search_requests
from .service import WebService


def main() -> int:
    parser = argparse.ArgumentParser(prog="aelix-webtool")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    search = sub.add_parser("search")
    search.add_argument("query", nargs="+")
    search.add_argument("--provider", default="auto")
    search.add_argument("--max-results", type=int, default=5)
    search.add_argument("--time-range")
    search.add_argument("--include-domain", action="append", default=[])
    search.add_argument("--exclude-domain", action="append", default=[])
    fetch = sub.add_parser("fetch")
    fetch.add_argument("url", nargs="+")
    fetch.add_argument("--max-chars", type=int, default=8000)
    fetch.add_argument("--offset", type=int, default=0)
    fetch.add_argument("--refresh", action="store_true")
    fetch.add_argument("--find", help="Find literal text in the fetched snapshot (one URL only)")
    args = parser.parse_args()
    service = WebService()
    try:
        if args.command == "status":
            print(service.status())
            return 0
        if args.command == "search":
            requests = search_requests(
                {
                    "queries": args.query,
                    "provider": args.provider,
                    "max_results": args.max_results,
                    "time_range": args.time_range,
                    "include_domains": args.include_domain,
                    "exclude_domains": args.exclude_domain,
                }
            )
            result = asyncio.run(
                service.search(requests[0]) if len(requests) == 1 else service.search_many(requests)
            )
        else:
            requests_fetch = fetch_requests(
                {
                    "urls": args.url,
                    "max_chars": args.max_chars,
                    "offset": args.offset,
                    "refresh": args.refresh,
                }
            )
            if args.find and len(requests_fetch) != 1:
                raise WebToolError("invalid_arguments", "--find requires one URL.")
            if args.find:
                FindRequest.from_args({"snapshot_id": "snap-" + "0" * 24, "query": args.find})
            result = asyncio.run(
                service.fetch(requests_fetch[0])
                if len(requests_fetch) == 1
                else service.fetch_many(requests_fetch)
            )
            if args.find:
                result = service.find(
                    FindRequest.from_args(
                        {"snapshot_id": result["snapshot_id"], "query": args.find}
                    )
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("is_error") else 0
    except WebToolError as exc:
        print(json.dumps({"error": exc.to_dict()}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
