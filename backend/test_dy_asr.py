"""Smoke: Douyin subtitles via cloud ASR (requires ASR_API_KEY)."""
import os

os.environ.setdefault("ASR_PROVIDER", "api")
os.environ.setdefault("ASR_MAX_DURATION_SEC", "180")

from app.subtitle_service import fetch_subtitles

url = "https://www.douyin.com/jingxuan?modal_id=7668087185878306067"
r = fetch_subtitles(url, 2000)
print("source", r.get("source"))
print("lang", r.get("language"))
print("engine", r.get("asr_engine"))
print("cues", len(r.get("cues") or []))
print((r.get("transcript") or "")[:400])
