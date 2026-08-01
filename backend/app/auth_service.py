"""Password hashing and JWT cookie helpers."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from fastapi import HTTPException, Request, Response

from . import db
from .membership import is_vip_user, subscription_public
from . import settings
from .settings import COOKIE_NAME, COOKIE_SECURE, JWT_EXPIRE_DAYS, JWT_SECRET
from .summary_config import FREE_DAILY_SUMMARIES
from .summary_quota import remaining_for_user

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    email = normalize_email(email)
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="请输入有效的邮箱地址")
    return email


def validate_password(password: str) -> str:
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="密码过长")
    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "email": email, "exp": exp}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=JWT_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def get_token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def get_optional_user(request: Request) -> Optional[Dict[str, Any]]:
    token = get_token_from_request(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    return db.get_user_by_id(user_id)


def require_user(request: Request) -> Dict[str, Any]:
    user = get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def stripe_configured() -> bool:
    settings.refresh_from_env()
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID)


def user_public(user: Dict[str, Any], *, client_ip: Optional[str] = None) -> Dict[str, Any]:
    del client_ip  # reserved for future anonymous hybrid display
    user_id = int(user["id"])
    sub = db.get_subscription_for_user(user_id)
    vip = is_vip_user(user_id)
    remaining: Optional[int] = None if vip else remaining_for_user(user_id)
    return {
        "id": user_id,
        "email": user["email"],
        "is_vip": vip,
        "subscription": subscription_public(sub),
        "remaining_summaries": remaining,
        "free_daily_summaries": FREE_DAILY_SUMMARIES,
        "stripe_configured": stripe_configured(),
    }
