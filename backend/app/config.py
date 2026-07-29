import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = Path(os.getenv("TEMP_DIR", str(BASE_DIR / "temp")))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_DOWNLOAD_BYTES = int(os.getenv("MAX_DOWNLOAD_BYTES", 500 * 1024 * 1024))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", 30))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", 60))
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 3))
TEMP_FILE_TTL_SEC = int(os.getenv("TEMP_FILE_TTL_SEC", 3600))
FREE_DAILY_PARSES = int(os.getenv("FREE_DAILY_PARSES", 999))


def resolve_ffmpeg_dir():
    """Return directory containing ffmpeg.exe, or None."""
    env = os.getenv("FFMPEG_PATH") or os.getenv("FFMPEG_BINARY")
    if env:
        p = Path(env)
        if p.is_file():
            return str(p.parent)
        if p.is_dir():
            return str(p)

    marker = BASE_DIR / "ffmpeg.path"
    if marker.exists():
        raw = marker.read_text(encoding="utf-8").strip().strip('"')
        if raw:
            p = Path(raw)
            if p.is_file() and p.name.lower().startswith("ffmpeg"):
                return str(p.parent)
            if p.is_dir() and (p / "ffmpeg.exe").exists():
                return str(p)
            if p.is_dir() and (p / "ffmpeg").exists():
                return str(p)

    # shutil.which fallback handled by callers via PATH
    return None


FFMPEG_DIR = resolve_ffmpeg_dir()
