"""VIP / subscription helpers."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from . import db

VIP_STATUSES = frozenset({"active", "trialing"})


def is_vip_subscription(sub: Optional[Dict[str, Any]]) -> bool:
    if not sub:
        return False
    status = str(sub.get("status") or "")
    if status not in VIP_STATUSES:
        return False
    period_end = float(sub.get("current_period_end") or 0)
    return period_end > time.time()


def is_vip_user(user_id: int) -> bool:
    return is_vip_subscription(db.get_subscription_for_user(user_id))


def subscription_public(sub: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not sub:
        return None
    return {
        "status": sub.get("status"),
        "current_period_end": sub.get("current_period_end"),
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
        "is_vip": is_vip_subscription(sub),
    }
