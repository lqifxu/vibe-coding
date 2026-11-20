"""Daily AI-summary quota (independent of download RateLimiter).

Branches:
- VIP user: unlimited (no consume)
- Logged-in free user: per user_id day counter in SQLite
- Anonymous: per IP day counter in SQLite
"""
from __future__ import annotations

import time
from typing import Optional

from . import db
from .limiter import RateLimitError
from .membership import is_vip_user
from .summary_config import FREE_DAILY_SUMMARIES


class SummaryQuota:
    def remaining_for_ip(self, ip: str) -> int:
        today = time.strftime("%Y-%m-%d")
        used = db.get_daily_usage("summary", "ip:{}".format(ip or "unknown"), today)
        return max(0, FREE_DAILY_SUMMARIES - used)

    def check_and_consume(self, ip: str) -> int:
        today = time.strftime("%Y-%m-%d")
        remaining = db.consume_daily_usage(
            "summary",
            "ip:{}".format(ip or "unknown"),
            today,
            FREE_DAILY_SUMMARIES,
        )
        if remaining is None:
            raise RateLimitError(
                "今日免费 AI 总结次数已用完（每日 {} 次）。升级 Pro 可解锁无限解析与 AI 总结。".format(
                    FREE_DAILY_SUMMARIES
                )
            )
        return remaining

    def check_and_consume_user(self, user_id: int) -> int:
        today = time.strftime("%Y-%m-%d")
        count = db.get_user_summary_count(user_id, today)
        if count >= FREE_DAILY_SUMMARIES:
            raise RateLimitError(
                "今日免费 AI 总结次数已用完（每日 {} 次）。升级 Pro 可解锁无限解析与 AI 总结。".format(
                    FREE_DAILY_SUMMARIES
                )
            )
        count += 1
        db.set_user_summary_count(user_id, today, count)
        return FREE_DAILY_SUMMARIES - count


summary_quota = SummaryQuota()


def remaining_for_user(user_id: int) -> int:
    return db.remaining_user_summaries(user_id, FREE_DAILY_SUMMARIES)


def remaining_for_ip(ip: str) -> int:
    return summary_quota.remaining_for_ip(ip)


def consume_summary_quota(
    *,
    user: Optional[dict],
    ip: str,
) -> Optional[int]:
    """
    Consume one summary quota.
    Returns remaining count, or None when VIP (unlimited).
    """
    if user:
        user_id = int(user["id"])
        if is_vip_user(user_id):
            return None
        return summary_quota.check_and_consume_user(user_id)
    return summary_quota.check_and_consume(ip)
