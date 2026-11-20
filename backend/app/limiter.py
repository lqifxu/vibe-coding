"""IP burst limiter plus a persisted daily parse counter."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, List

from . import db
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

    def remaining_daily_parse(self, subject: str) -> int:
        """Remaining free parses today. Does not consume a credit."""
        today = time.strftime("%Y-%m-%d")
        used = db.get_daily_usage("parse", subject, today)
        return max(0, FREE_DAILY_PARSES - used)

    def check_daily_parse(self, subject: str) -> int:
        today = time.strftime("%Y-%m-%d")
        remaining = db.consume_daily_usage("parse", subject, today, FREE_DAILY_PARSES)
        if remaining is None:
            raise RateLimitError(
                "今日免费解析次数已用完（每日 {} 次）。升级 Pro 可解锁无限解析与 AI 总结。".format(
                    FREE_DAILY_PARSES
                )
            )
        return remaining


rate_limiter = RateLimiter()
download_semaphore = threading.Semaphore(MAX_CONCURRENT_DOWNLOADS)