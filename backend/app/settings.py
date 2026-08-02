"""Shared env settings for auth / billing / DB (loads backend/.env)."""
from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    path = _BACKEND_ROOT / ".env"
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip().lstrip("\ufeff")
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            force = (
                key.startswith("JWT_")
                or key.startswith("STRIPE_")
                or key.startswith("DATABASE_")
                or key.startswith("FREE_DAILY_")
                or key.startswith("ASR_")
                or key == "PUBLIC_APP_URL"
                or key == "COOKIE_SECURE"
            )
            if force:
                os.environ[key] = val
            elif key not in os.environ or not str(os.environ.get(key, "")).strip():
                os.environ[key] = val
    except OSError:
        pass


def refresh_from_env() -> None:
    """Re-read .env into module globals (so key updates apply without full restart)."""
    global DATABASE_PATH, JWT_SECRET, JWT_EXPIRE_DAYS, COOKIE_SECURE
    global STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID, PUBLIC_APP_URL

    _load_dotenv()

    path = Path(os.getenv("DATABASE_PATH", str(_BACKEND_ROOT / "data" / "app.db"))).expanduser()
    if not path.is_absolute():
        path = (_BACKEND_ROOT / path).resolve()
    DATABASE_PATH = path

    JWT_SECRET = (
        os.getenv("JWT_SECRET", "").strip()
        or "dev-only-change-me-jisuxia-jwt-secret-32b+"
    )
    JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")

    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()
    PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:5173").rstrip("/")


refresh_from_env()

COOKIE_NAME = "jisuxia_session"
