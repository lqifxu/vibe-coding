"""Lightweight IP rate limiter and daily parse counter (in-memory, no DB)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from .config import (
    FREE_DAILY_PARSES,
    MAX_CONCURRENT_DOWNLOADS,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SEC,
)


class RateLimitError(Exception):
    pass


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits = defaultdict(list)  # type: Dict[str, List[float]]
        self._daily = {}  # type: Dict[str, Tuple[str, int]]

    def check_rate(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            window = self._hits[ip]
            self._hits[ip] = [t for t in window if now - t < RATE_LIMIT_WINDOW_SEC]
            if len(self._hits[ip]) >= RATE_LIMIT_REQUESTS:
                raise RateLimitError(
                    "请求过于频繁，请稍后再试。升级 Pro 可获得更高配额。"
                )
            self._hits[ip].append(now)

    def check_daily_parse(self, ip: str) -> int:
        today = time.strftime("%Y-%m-%d")
        with self._lock:
            day, count = self._daily.get(ip, (today, 0))
            if day != today:
                count = 0
                day = today
            if count >= FREE_DAILY_PARSES:
                raise RateLimitError(
                    "今日免费解析次数已用完。升级 Pro 可无限解析。"
                )
            count += 1
            self._daily[ip] = (day, count)
            return FREE_DAILY_PARSES - count


rate_limiter = RateLimiter()
download_semaphore = threading.Semaphore(MAX_CONCURRENT_DOWNLOADS)
