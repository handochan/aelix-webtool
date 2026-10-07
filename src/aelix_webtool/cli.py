"""A model-free CLI for diagnostics and live provider smoke tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .errors import WebToolError
from .models import FetchRequest, SearchRequest
from .service import WebService


def main() -> int:
    parser = argparse.ArgumentParser(prog="aelix-webtool")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--provider", default="auto")
    search.add_argument("--max-results", type=int, default=5)
    search.add_argument("--time-range")
    search.add_argument("--include-domain", action="append", default=[])
    search.add_argument("--exclude-domain", action="append", default=[])
    fetch = sub.add_parser("fetch")
    fetch.add_argument("url")
    fetch.add_argument("--max-chars", type=int, default=8000)
    fetch.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    service = WebService()
    try:
        if args.command == "status":
            print(service.status())
            return 0
        if args.command == "search":
            request = SearchRequest.from_args(
                {
                    "query": args.query,
                    "provider": args.provider,
                    "max_results": args.max_results,
                    "time_range": args.time_range,
                    "include_domains": args.include_domain,
                    "exclude_domains": args.exclude_domain,
                }
            )
            result = asyncio.run(service.search(request))
        else:
            request_fetch = FetchRequest.from_args(
                {"url": args.url, "max_chars": args.max_chars, "offset": args.offset}
            )
            result = asyncio.run(service.fetch(request_fetch))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except WebToolError as exc:
        print(json.dumps({"error": exc.to_dict()}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
