"""Operator-owned settings. Models cannot supply credentials or API endpoints."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import WebToolError

PROVIDERS = ("searxng", "brave", "tavily", "exa", "duckduckgo")
KEY_ENV = {"brave": "BRAVE_API_KEY", "tavily": "TAVILY_API_KEY", "exa": "EXA_API_KEY"}


@dataclass(frozen=True)
class Config:
    provider: str = "auto"
    keys: Mapping[str, str] = field(default_factory=dict, repr=False)
    searxng_url: str = field(default="", repr=False)
    offline: bool = False
    retries: int = 0
    fallback_providers: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env
        return cls(
            provider=env.get("AELIX_WEB_PROVIDER", "auto").strip().lower(),
            keys={p: env[k].strip() for p, k in KEY_ENV.items() if env.get(k, "").strip()},
            searxng_url=env.get("AELIX_WEB_SEARXNG_URL", "").strip(),
            offline=env.get("AELIX_WEB_OFFLINE", "").strip().lower() in {"1", "true", "yes"},
            retries=int(env.get("AELIX_WEB_RETRIES", "0").strip())
            if env.get("AELIX_WEB_RETRIES", "0").strip() in {"0", "1"}
            else -1,
            fallback_providers=tuple(
                v.strip().lower()
                for v in env.get("AELIX_WEB_FALLBACK_PROVIDERS", "").split(",")
                if v.strip()
            ),
        )

    def available(self) -> list[str]:
        return [
            p
            for p in PROVIDERS
            if p == "duckduckgo" or (self.searxng_url if p == "searxng" else self.keys.get(p))
        ]

    def select(self, requested: str = "auto") -> str:
        if self.offline:
            raise WebToolError("offline", "Web tools are disabled by AELIX_WEB_OFFLINE.")
        provider = self.provider if requested == "auto" else requested
        if provider not in (*PROVIDERS, "auto"):
            raise WebToolError(
                "configuration",
                "AELIX_WEB_PROVIDER must be auto, searxng, brave, tavily, exa or duckduckgo.",
            )
        available = self.available()
        if provider == "auto":
            # DuckDuckGo is selectable without keys or an operator endpoint.
            # This is selection before I/O, never failover after an error.
            return available[0]
        if provider not in available:
            name = "AELIX_WEB_SEARXNG_URL" if provider == "searxng" else KEY_ENV[provider]
            raise WebToolError(
                "not_configured", f"Set {name} to use {provider}. No search request was sent."
            )
        return provider

    def route(self, requested: str = "auto") -> tuple[str, ...]:
        primary = self.select(requested)
        if type(self.retries) is not int or self.retries not in {0, 1}:
            raise WebToolError("configuration", "AELIX_WEB_RETRIES must be 0 or 1.")
        if requested != "auto":
            return (primary,)
        fallbacks = self.fallback_providers
        if len(fallbacks) > 2 or len(set(fallbacks)) != len(fallbacks) or primary in fallbacks:
            raise WebToolError(
                "configuration",
                "Specify at most two unique fallback providers, excluding the primary provider.",
            )
        for provider in fallbacks:
            if provider not in PROVIDERS:
                raise WebToolError(
                    "configuration", "Unknown operator-configured fallback provider."
                )
            self.select(provider)
        return (primary, *fallbacks)
