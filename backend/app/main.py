"""FastAPI entry - thin HTTP layer over yt-dlp."""
from __future__ import annotations

import logging
import mimetypes
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .auth_router import router as auth_router
from .auth_service import get_optional_user
from .billing_router import router as billing_router
from .cleanup import remove_dir, start_cleanup_loop
from .config import FREE_DAILY_PARSES
from .db import init_db
from .limiter import RateLimitError, download_semaphore, rate_limiter
from .membership import is_vip_user
from .settings import PUBLIC_APP_URL
from .summary_router import router as summary_router
from .ytdlp_service import (
    YtdlpError,
    check_ffmpeg_cli,
    download_video,
    extract_info,
    ffmpeg_available,
    validate_url,
    ytdlp_version,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="极速下 API", version="0.2.0")

_cors_origins = list(
    dict.fromkeys(
        [
            PUBLIC_APP_URL,
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(billing_router)
# AI summary extension (OCP mount)
app.include_router(summary_router)


class UrlBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class DownloadBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    format_id: str = Field(default="best", max_length=128)


def _client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@app.on_event("startup")
def on_startup():
    init_db()
    start_cleanup_loop()
    logger.info(
        "cleanup loop started; yt-dlp=%s ffmpeg=%s db=%s",
        ytdlp_version(),
        ffmpeg_available(),
        "ok",
    )


@app.exception_handler(YtdlpError)
async def ytdlp_error_handler(_request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RateLimitError)
async def rate_limit_handler(_request, exc):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


def _parse_subject(user, ip: str) -> str:
    if user:
        return "user:{}".format(int(user["id"]))
    return "ip:{}".format(ip or "unknown")


@app.get("/api/health")
def health(request: Request):
    from .asr_service import asr_api_configured, asr_available, asr_provider

    user = get_optional_user(request)
    vip = bool(user and is_vip_user(int(user["id"])))
    remaining = None if vip else rate_limiter.remaining_daily_parse(_parse_subject(user, _client_ip(request)))
    return {
        "ok": True,
        "code_rev": "20261120e",
        "yt_dlp": ytdlp_version(),
        "ffmpeg": ffmpeg_available(),
        "ffmpeg_detail": check_ffmpeg_cli(),
        "free_daily_parses": FREE_DAILY_PARSES,
        "remaining_parses": remaining,
        "is_vip": vip,
        "asr": asr_available(),
        "asr_provider": asr_provider(),
        "asr_api": asr_api_configured(),
    }


@app.post("/api/info")
def api_info(body: UrlBody, request: Request):
    ip = _client_ip(request)
    rate_limiter.check_rate(ip)
    user = get_optional_user(request)
    if user and is_vip_user(int(user["id"])):
        remaining = None  # Pro: unlimited parses
    else:
        remaining = rate_limiter.check_daily_parse(_parse_subject(user, ip))
    url = validate_url(body.url)
    info = extract_info(url)
    info["remaining_parses"] = remaining
    info["is_vip"] = remaining is None
    return info


@app.post("/api/download")
def api_download(body: DownloadBody, request: Request, background_tasks: BackgroundTasks):
    ip = _client_ip(request)
    rate_limiter.check_rate(ip)
    url = validate_url(body.url)
    format_id = (body.format_id or "best").strip()

    acquired = download_semaphore.acquire(blocking=False)
    if not acquired:
        raise YtdlpError("服务器繁忙，请稍后再试。升级 Pro 可解锁下载队列。", status_code=503)

    try:
        media_path = download_video(url, format_id)
    finally:
        download_semaphore.release()

    job_dir = media_path.parent
    background_tasks.add_task(remove_dir, job_dir)

    mime, _ = mimetypes.guess_type(str(media_path))
    filename = media_path.name
    disposition = "attachment; filename*=UTF-8''{}".format(quote(filename))

    return FileResponse(
        path=str(media_path),
        media_type=mime or "application/octet-stream",
        filename=filename,
        headers={"Content-Disposition": disposition},
    )
