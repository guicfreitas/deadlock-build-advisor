"""Thin client for the community Deadlock API (https://api.deadlock-api.com).

Zero third-party deps: urllib + a small on-disk JSON cache so repeated
recommendations (same hero/enemies) do not burn the shared rate limit.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from . import i18n

BASE_URL = "https://api.deadlock-api.com"
USER_AGENT = "deadlock-build-advisor/0.1"


class ApiError(RuntimeError):
    pass


def since_days(days: int) -> int:
    """Unix time `days` ago, rounded down to the day: the URL (and so the CDN cache) stays
    the same all day."""
    return (int(time.time()) // 86400 - days) * 86400


class DeadlockApi:
    def __init__(self, cache_dir: Path, api_key: str | None = None, cache_ttl_s: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or None
        self.cache_ttl_s = cache_ttl_s

    # ------------------------------------------------------------------ http
    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    @staticmethod
    def _url(path: str, params: dict[str, Any] | None) -> str:
        clean = {}
        for k, v in (params or {}).items():
            if v is None:
                continue
            if isinstance(v, bool):
                v = "true" if v else "false"
            elif isinstance(v, (list, tuple, set)):
                v = ",".join(str(x) for x in v)
            clean[k] = v
        q = urllib.parse.urlencode(sorted(clean.items()))
        return f"{BASE_URL}{path}" + (f"?{q}" if q else "")

    def get(self, path: str, params: dict[str, Any] | None = None, *, ttl_s: int | None = None,
            retries: int = 3, timeout: float = 60) -> Any:
        url = self._url(path, params)
        ttl = self.cache_ttl_s if ttl_s is None else ttl_s
        cache_file = self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if ttl > 0 and cache_file.exists() and time.time() - cache_file.stat().st_mtime < ttl:
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass

        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=self._headers())
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if ttl > 0:
                    cache_file.write_text(json.dumps(data), encoding="utf-8")
                return data
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:300]
                last_err = ApiError(f"HTTP {e.code} em {path}: {body}")
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_err from e
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                last_err = ApiError(f"Falha de rede em {path}: {e}")
                time.sleep(1 + attempt)
        # stale cache is better than nothing mid-match
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        raise last_err or ApiError(f"Falha em {path}")

    def stream_sse(self, path: str, params: dict[str, Any], timeout: float = 90) -> Iterator[tuple[str, Any]]:
        """Yield (event, data) tuples from a Server-Sent Events endpoint."""
        url = self._url(path, params)
        headers = self._headers() | {"Accept": "text/event-stream"}
        req = urllib.request.Request(url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            raise ApiError(f"HTTP {e.code} em {path}: {e.read().decode('utf-8', 'replace')[:300]}") from e
        with resp:
            event, data_lines = "message", []
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if not line:
                    if data_lines:
                        payload = "\n".join(data_lines)
                        try:
                            yield event, json.loads(payload)
                        except ValueError:
                            yield event, payload
                    event, data_lines = "message", []
                    continue
                if line.startswith(":"):
                    yield "ping", None  # keep-alive: lets callers check their timers
                    continue
                key, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if key == "event":
                    event = value
                elif key == "data":
                    data_lines.append(value)

    # ------------------------------------------------------------- endpoints
    def heroes(self) -> list[dict]:
        return self.get("/v1/assets/heroes", {"only_active": True, "language": i18n.api_language()}, ttl_s=24 * 3600)

    def upgrade_items(self) -> list[dict]:
        return self.get("/v1/assets/items/by-type/upgrade", {"language": i18n.api_language()}, ttl_s=24 * 3600)

    def analytics(self, path: str, params: dict[str, Any], **kw) -> Any:
        """Heavy queries over the API's default 30-day window can time out (HTTP 504, and the
        CDN then serves that 504 for the same URL); 14 days is enough data and answers fast."""
        try:
            return self.get(path, params, **kw)
        except ApiError as e:
            if "HTTP 504" not in str(e) or "min_unix_timestamp" in params:
                raise
            return self.get(path, params | {"min_unix_timestamp": since_days(14)}, **kw)

    def item_stats(self, **params) -> list[dict]:
        return self.analytics("/v1/analytics/item-stats", params)

    def ability_order_tree(self, days: int = 14, **params) -> list[dict]:
        """The default 30-day window times out for this one (see analytics); 14 days answers
        in ~2 s with ~0.5 MB."""
        return self.get("/v1/analytics/ability-order-tree",
                        {"min_matches": 500, "min_unix_timestamp": since_days(days)} | params,
                        ttl_s=12 * 3600)

    def ability(self, ability_id: int) -> dict:
        # one asset at a time: the whole ability list is ~4 MB
        return self.get(f"/v1/assets/items/{int(ability_id)}", {"language": i18n.api_language()}, ttl_s=24 * 3600)

    def hero_counter_stats(self, **params) -> list[dict]:
        return self.analytics("/v1/analytics/hero-counter-stats", params)

    def active_matches(self, account_id: int) -> list[dict]:
        return self.get("/v1/matches/active", {"account_id": account_id}, ttl_s=0)
