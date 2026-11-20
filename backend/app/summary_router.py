"""AI summary APIRouter — mount via app.include_router (OCP)."""
from __future__ import annotations

import json
import re
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .auth_service import get_optional_user
from .limiter import rate_limiter
from .llm_service import llm_configured
from .membership import is_vip_user
from .summary_config import FREE_DAILY_SUMMARIES, MAX_SUMMARY_CHARS
from .summary_jobs import ask_job, ask_job_stream, create_job, get_job, iter_summary_sse
from .summary_quota import consume_summary_quota, remaining_for_ip, remaining_for_user
from .subtitle_service import export_subtitles, fetch_subtitles
from .ytdlp_service import YtdlpError, validate_url

router = APIRouter(tags=["summary"])


class SummarizeBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class SubtitlesBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    format: str = Field(default="srt", max_length=8)


class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


_SAFE_FILENAME = re.compile(r'[\\/:*?"<>|\s]+')


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.get("/api/summary/meta")
def summary_meta(request: Request):
    user = get_optional_user(request)
    vip = bool(user and is_vip_user(int(user["id"])))
    if vip:
        remaining = None
    elif user:
        remaining = remaining_for_user(int(user["id"]))
    else:
        remaining = remaining_for_ip(_client_ip(request))
    return {
        "llm_configured": llm_configured(),
        "free_daily_summaries": FREE_DAILY_SUMMARIES,
        "remaining_summaries": remaining,
        "is_vip": vip,
        "provider_hint": "deepseek",
    }


@router.post("/api/summarize")
def api_summarize(body: SummarizeBody, request: Request):
    ip = _client_ip(request)
    rate_limiter.check_rate(ip)
    if not llm_configured():
        raise YtdlpError(
            "未配置 LLM_API_KEY（或 DEEPSEEK_API_KEY），无法生成 AI 总结。"
            "请设置环境变量后重启后端。",
            status_code=503,
        )
    user = get_optional_user(request)
    remaining = consume_summary_quota(user=user, ip=ip)
    url = validate_url(body.url)
    job_id = create_job(url)
    return {"job_id": job_id, "remaining_summaries": remaining, "is_vip": remaining is None}


@router.post("/api/subtitles")
def api_subtitles(body: SubtitlesBody, request: Request):
    """Fetch captions and return a downloadable SRT/VTT/TXT file (no LLM / no summary quota)."""
    ip = _client_ip(request)
    rate_limiter.check_rate(ip)
    url = validate_url(body.url)
    # Generous cap for file download (still bounded).
    max_chars = max(MAX_SUMMARY_CHARS, 200000)
    sub = fetch_subtitles(url, max_chars)
    cues = sub.get("cues") or []
    if not cues and (body.format or "srt").lower() != "txt":
        raise YtdlpError("未获取到可用字幕条目。", status_code=422)
    text_body, media_type, ext = export_subtitles(
        cues,
        body.format or "srt",
        transcript=sub.get("transcript"),
    )
    title = _SAFE_FILENAME.sub("_", (sub.get("title") or "subtitles")[:40]).strip("_") or "subtitles"
    filename = "{}.{}".format(title, ext)
    disposition = "attachment; filename*=UTF-8''{}".format(quote(filename))
    return Response(
        content=text_body.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


@router.get("/api/summarize/{job_id}")
def api_summarize_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"detail": "任务不存在或已过期"})
    return {
        "job_id": job["id"],
        "status": job["status"],
        "stage": job.get("stage"),
        "result": job.get("result"),
        "stream_markdown": job.get("stream_markdown") or "",
        "error": job.get("error"),
    }


@router.get("/api/summarize/{job_id}/events")
def api_summarize_events(job_id: str):
    """SSE: push job snapshots while summarizing (for streaming UI).

    Douyin ASR can sit in ``fetching_subtitles`` for minutes with an unchanged
    payload. Use a wall-clock deadline (not a short unchanged-payload idle
    counter) so long-running jobs are not reported as ``等待超时``.
    """

    def event_stream():
        # Each LLM token is its own SSE event. Do not buffer into snapshots.
        for kind, payload in iter_summary_sse(job_id):
            if kind == "keepalive":
                yield ": keepalive\n\n"
                continue
            if kind == "delta":
                yield "event: delta\ndata: {}\n\n".format(
                    json.dumps(payload, ensure_ascii=False)
                )
                continue
            if kind == "timeout":
                yield "event: error\ndata: {}\n\n".format(
                    json.dumps(payload, ensure_ascii=False)
                )
                return
            if kind == "error":
                yield "event: error\ndata: {}\n\n".format(
                    json.dumps(payload, ensure_ascii=False)
                )
                return
            event_name = "end" if kind == "end" else "update"
            yield "event: {}\ndata: {}\n\n".format(
                event_name,
                json.dumps(payload, ensure_ascii=False),
            )
            if kind in ("sync", "end") and (payload or {}).get("status") in ("done", "failed"):
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/summarize/{job_id}/ask")
def api_summarize_ask(job_id: str, body: AskBody, request: Request):
    ip = _client_ip(request)
    rate_limiter.check_rate(ip)
    answer = ask_job(job_id, body.question)
    return {"answer": answer}


@router.post("/api/summarize/{job_id}/ask/stream")
def api_summarize_ask_stream(job_id: str, body: AskBody, request: Request):
    ip = _client_ip(request)
    rate_limiter.check_rate(ip)

    def gen():
        try:
            for delta in ask_job_stream(job_id, body.question):
                yield "data: {}\n\n".format(json.dumps({"delta": delta}, ensure_ascii=False))
            yield "data: {}\n\n".format(json.dumps({"done": True}, ensure_ascii=False))
        except YtdlpError as exc:
            yield "data: {}\n\n".format(
                json.dumps({"error": exc.message}, ensure_ascii=False)
            )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
