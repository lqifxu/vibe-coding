"""Daily AI-summary quota (independent of download RateLimiter)."""
from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

from .limiter import RateLimitError
from .summary_config import FREE_DAILY_SUMMARIES


class SummaryQuota:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._daily: Dict[str, Tuple[str, int]] = {}

    def check_and_consume(self, ip: str) -> int:
        today = time.strftime("%Y-%m-%d")
        with self._lock:
            day, count = self._daily.get(ip, (today, 0))
            if day != today:
                count = 0
                day = today
            if count >= FREE_DAILY_SUMMARIES:
                raise RateLimitError(
                    "今日免费 AI 总结次数已用完。升级 Pro 可解锁更高配额。"
                )
            count += 1
            self._daily[ip] = (day, count)
            return FREE_DAILY_SUMMARIES - count


summary_quota = SummaryQuota()
