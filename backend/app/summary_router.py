"""AI summary APIRouter — mount via app.include_router (OCP)."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .limiter import rate_limiter
from .llm_service import llm_configured
from .summary_config import FREE_DAILY_SUMMARIES, MAX_SUMMARY_CHARS
from .summary_jobs import ask_job, ask_job_stream, create_job, get_job
from .summary_quota import summary_quota
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
def summary_meta():
    return {
        "llm_configured": llm_configured(),
        "free_daily_summaries": FREE_DAILY_SUMMARIES,
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
    remaining = summary_quota.check_and_consume(ip)
    url = validate_url(body.url)
    job_id = create_job(url)
    return {"job_id": job_id, "remaining_summaries": remaining}


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
    """SSE: push job snapshots while summarizing (for streaming UI)."""

    def event_stream():
        last = None
        idle = 0
        while idle < 180:
            job = get_job(job_id)
            if not job:
                yield "event: error\ndata: {}\n\n".format(
                    json.dumps({"detail": "任务不存在或已过期"}, ensure_ascii=False)
                )
                return
            payload = {
                "job_id": job["id"],
                "status": job["status"],
                "stage": job.get("stage"),
                "result": job.get("result"),
                "stream_markdown": job.get("stream_markdown") or "",
                "error": job.get("error"),
            }
            blob = json.dumps(payload, ensure_ascii=False)
            if blob != last:
                last = blob
                yield "event: update\ndata: {}\n\n".format(blob)
                idle = 0
            else:
                idle += 1
            if job["status"] in ("done", "failed"):
                yield "event: end\ndata: {}\n\n".format(blob)
                return
            time.sleep(0.12)

        yield "event: error\ndata: {}\n\n".format(
            json.dumps({"detail": "等待超时"}, ensure_ascii=False)
        )

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
