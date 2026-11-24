"""Rate-limited HTTP client for free public SEC endpoints.

* Sends the descriptive User-Agent the SEC requires.
* Never exceeds 10 requests/second (SEC fair-access policy); default is 5.
* Caches responses locally. Files inside an EDGAR accession folder never change,
  so they are cached forever; indexes and search results are refreshed after a TTL.
* The transport is injectable, so tests and the offline demo never touch the network.
"""

from __future__ import annotations

import gzip
import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional, Tuple

from .cache import HttpCache

Transport = Callable[[str, dict, float], Tuple[int, str, bytes]]

RETRY_STATUSES = {429, 500, 502, 503, 504}
_IMMUTABLE = re.compile(r"/Archives/edgar/data/\d+/\d{18}/")


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, hint: str = "") -> None:
        message = f"HTTP {status} for {url}" if status else f"Network error for {url}"
        if hint:
            message += f" ({hint})"
        super().__init__(message)
        self.status = status
        self.url = url


def urllib_transport(url: str, headers: dict, timeout: float) -> Tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, hdrs, body = resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        status, hdrs, body = exc.code, exc.headers, exc.read() or b""
    if hdrs is not None and "gzip" in (hdrs.get("Content-Encoding") or "").lower():
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
    return status, (hdrs.get("Content-Type", "") if hdrs is not None else ""), body


class RateLimiter:
    def __init__(self, max_rps: float, sleep: Callable[[float], None] = time.sleep) -> None:
        self.interval = 1.0 / max(0.1, min(float(max_rps), 10.0))
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            if delay > 0:
                self._sleep(delay)
                now = time.monotonic()
            self._next = max(now, self._next) + self.interval


class SecClient:
    def __init__(
        self,
        user_agent: str,
        cache: Optional[HttpCache] = None,
        *,
        max_rps: float = 5.0,
        ttl_hours: float = 6.0,
        transport: Optional[Transport] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError("SEC requires a descriptive User-Agent with a contact email, e.g. 'Jane Doe jane@yourfirm.com'")
        self.user_agent = user_agent
        self.cache = cache
        self.ttl_hours = ttl_hours
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport or urllib_transport
        self._sleep = sleep
        self._limiter = RateLimiter(max_rps, sleep=sleep)
        self.stats = {"network": 0, "cache_hits": 0}

    def ttl_for(self, url: str) -> Optional[float]:
        """Seconds a cached copy stays fresh; None means forever (immutable filing documents)."""
        if _IMMUTABLE.search(url):
            return None
        if "company_tickers" in url:
            return 24 * 3600.0
        return self.ttl_hours * 3600.0

    def get(self, url: str, *, use_cache: bool = True) -> bytes:
        if self.cache is not None and use_cache:
            hit = self.cache.get(url, self.ttl_for(url))
            if hit is not None:
                self.stats["cache_hits"] += 1
                return hit.body

        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip",
            "Accept": "application/json, application/xml, text/xml, */*",
        }
        attempt = 0
        while True:
            self._limiter.wait()
            try:
                status, content_type, body = self._transport(url, headers, self.timeout)
            except OSError as exc:  # DNS failure, timeout, connection reset ...
                if attempt < self.max_retries:
                    self._sleep(2 ** attempt)
                    attempt += 1
                    continue
                raise HttpError(0, url, str(exc)) from exc
            self.stats["network"] += 1
            if status in RETRY_STATUSES and attempt < self.max_retries:
                self._sleep(2 ** attempt)
                attempt += 1
                continue
            break

        if status != 200:
            hint = ""
            if status == 403 and "sec.gov" in url:
                hint = "SEC refused the request: check SEC_USER_AGENT (name + email) and keep SEC_MAX_RPS at 10 or below"
            elif status == 404:
                hint = "not found"
            raise HttpError(status, url, hint)

        if self.cache is not None:
            self.cache.put(url, status, content_type, body)
        return body

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return json.loads(self.get(url, **kwargs).decode("utf-8"))
