"""AI summary extension config (OpenAI-compatible; default DeepSeek)."""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load backend/.env into os.environ (file values override empty shell vars)."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            # Always apply from .env for LLM/summary keys so local .env wins
            if (
                key.startswith("LLM_")
                or key.startswith("DEEPSEEK_")
                or key.startswith("FREE_DAILY_SUMMARIES")
                or key.startswith("SUMMARY_")
                or key.startswith("MAX_SUMMARY")
                or key.startswith("MAX_CONCURRENT_SUMMARIES")
                or key.startswith("BILI_")
                or key.startswith("BILIBILI_")
                or key.startswith("ASR_")
                or key == "SESSDATA"
            ):
                os.environ[key] = val
            elif key not in os.environ or not str(os.environ.get(key, "")).strip():
                os.environ[key] = val
    except OSError:
        pass


_load_dotenv()

LLM_API_KEY = (
    os.getenv("LLM_API_KEY", "").strip()
    or os.getenv("DEEPSEEK_API_KEY", "").strip()
)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat").strip() or "deepseek-chat"
FREE_DAILY_SUMMARIES = int(os.getenv("FREE_DAILY_SUMMARIES", "999"))
SUMMARY_JOB_TTL_SEC = int(os.getenv("SUMMARY_JOB_TTL_SEC", "3600"))
MAX_SUMMARY_CHARS = int(os.getenv("MAX_SUMMARY_CHARS", "80000"))
MAX_CONCURRENT_SUMMARIES = int(os.getenv("MAX_CONCURRENT_SUMMARIES", "2"))