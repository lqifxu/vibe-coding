"""In-memory async jobs for AI video summary."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from typing import Any, Dict, Iterator, Optional, Tuple

from .summary_config import (
    MAX_CONCURRENT_SUMMARIES,
    MAX_SUMMARY_CHARS,
    SUMMARY_JOB_TTL_SEC,
)
from .llm_service import (
    answer_question,
    answer_question_streaming,
    build_mindmap,
    llm_configured,
    summarize_transcript_streaming,
)
from .subtitle_service import fetch_subtitles
from .ytdlp_service import YtdlpError

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}
_summary_semaphore = threading.Semaphore(MAX_CONCURRENT_SUMMARIES)


def _purge_expired() -> None:
    now = time.time()
    expired = [jid for jid, job in _jobs.items() if now - job.get("created_at", 0) > SUMMARY_JOB_TTL_SEC]
    for jid in expired:
        _jobs.pop(jid, None)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        _purge_expired()
        job = _jobs.get(job_id)
        if not job:
            return None
        return dict(job)


def create_job(url: str) -> str:
    if not llm_configured():
        raise YtdlpError(
            "未配置 LLM_API_KEY，无法生成 AI 总结。请在后端环境变量中配置 OpenAI 兼容密钥。",
            status_code=503,
        )
    job_id = str(uuid.uuid4())
    with _lock:
        _purge_expired()
        job = {
            "id": job_id,
            "url": url,
            "status": "queued",
            "stage": None,
            "result": None,
            "error": None,
            "stream_markdown": "",
            "transcript": "",
            "created_at": time.time(),
            "events": deque(maxlen=8000),
            "event_seq": 0,
        }
        job["cond"] = threading.Condition(_lock)
        _jobs[job_id] = job
    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    thread.start()
    return job_id


def _public_view(job: Dict[str, Any], include_markdown: bool = False) -> Dict[str, Any]:
    result = job.get("result")
    view = {
        "job_id": job["id"],
        "status": job["status"],
        "stage": job.get("stage"),
        "result": dict(result) if isinstance(result, dict) else result,
        "error": job.get("error"),
    }
    if include_markdown:
        view["stream_markdown"] = job.get("stream_markdown") or ""
    return view


def _publish_locked(job: Dict[str, Any], kind: str, data: Any) -> None:
    job["event_seq"] = int(job.get("event_seq") or 0) + 1
    job["events"].append((job["event_seq"], kind, data))
    cond = job.get("cond")
    if cond is not None:
        cond.notify_all()


def _update(job_id: str, **fields: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.update(fields)
        done = job.get("status") in ("done", "failed")
        _publish_locked(job, "status", _public_view(job, include_markdown=done))


def publish_delta(job_id: str, delta: str) -> None:
    if not delta:
        return
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["stream_markdown"] = (job.get("stream_markdown") or "") + delta
        result = job.get("result")
        if isinstance(result, dict):
            result["stream_markdown"] = job["stream_markdown"]
        _publish_locked(job, "delta", delta)


def iter_summary_sse(job_id: str, deadline_sec: float = 300) -> Iterator[Tuple[str, Any]]:
    """Push sync, then each token as soon as it is published. No polling."""
    deadline = time.time() + deadline_sec
    with _lock:
        _purge_expired()
        job = _jobs.get(job_id)
        if not job:
            sync = None
            last_seq = 0
        else:
            last_seq = int(job.get("event_seq") or 0)
            sync = _public_view(job, include_markdown=True)
    if sync is None:
        yield ("error", {"detail": "任务不存在或已过期"})
        return
    yield ("sync", sync)
    if sync.get("status") in ("done", "failed"):
        return

    while time.time() < deadline:
        with _lock:
            job = _jobs.get(job_id)
            if not job:
                missing = True
                fresh = []
                status = None
            else:
                missing = False
                fresh = [item for item in job["events"] if item[0] > last_seq]
                if not fresh and job.get("status") not in ("done", "failed"):
                    remaining = max(0.05, min(15.0, deadline - time.time()))
                    job["cond"].wait(timeout=remaining)
                    fresh = [item for item in job["events"] if item[0] > last_seq]
                status = job.get("status")
        if missing:
            yield ("error", {"detail": "任务不存在或已过期"})
            return
        if fresh:
            for seq, kind, data in fresh:
                last_seq = seq
                if kind == "delta":
                    yield ("delta", {"delta": data})
                    continue
                view = data if isinstance(data, dict) else {}
                if view.get("status") in ("done", "failed"):
                    yield ("end", view)
                    return
                yield ("status", view)
            if status in ("done", "failed"):
                return
            continue
        if status in ("done", "failed"):
            with _lock:
                job = _jobs.get(job_id)
                view = _public_view(job, include_markdown=True) if job else None
            if view:
                yield ("end", view)
            return
        if time.time() >= deadline:
            break
        yield ("keepalive", None)

    yield (
        "timeout",
        {
            "detail": "任务仍在后台处理，可继续刷新或凭 job_id 恢复查询",
            "job_id": job_id,
            "soft_timeout": True,
        },
    )


def _merge_result(job_id: str, patch: Dict[str, Any], stream_markdown: str = "") -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        current = dict(job.get("result") or {})
        current.update(patch)
        if stream_markdown:
            job["stream_markdown"] = stream_markdown
            current["stream_markdown"] = stream_markdown
        # keep mindmap fresh when outline/highlights change
        if current.get("outline") is not None or current.get("highlights") is not None:
            current["mindmap"] = build_mindmap(
                current.get("title") or "",
                current.get("outline") or [],
                current.get("highlights") or [],
            )
        job["result"] = current


def ask_job(job_id: str, question: str) -> str:
    job = get_job(job_id)
    if not job:
        raise YtdlpError("任务不存在或已过期", status_code=404)
    transcript = job.get("transcript") or ""
    result = job.get("result") or {}
    if not transcript:
        raise YtdlpError("字幕尚未就绪，请等总结完成后再提问。", status_code=409)
    title = result.get("title") or "视频"
    hint = result.get("overview") or result.get("summary") or ""
    return answer_question(title, transcript, question, summary_hint=hint)


def ask_job_stream(job_id: str, question: str):
    job = get_job(job_id)
    if not job:
        raise YtdlpError("任务不存在或已过期", status_code=404)
    transcript = job.get("transcript") or ""
    result = job.get("result") or {}
    if not transcript:
        raise YtdlpError("字幕尚未就绪，请等总结完成后再提问。", status_code=409)
    title = result.get("title") or "视频"
    hint = result.get("overview") or result.get("summary") or ""
    return answer_question_streaming(title, transcript, question, summary_hint=hint)


def _run_job(job_id: str) -> None:
    acquired = _summary_semaphore.acquire(blocking=True, timeout=300)
    if not acquired:
        _update(job_id, status="failed", error="服务器繁忙，请稍后重试。", stage=None)
        return

    try:
        with _lock:
            job = _jobs.get(job_id)
            url = job["url"] if job else None
        if not url:
            return

        _update(job_id, status="running", stage="fetching_subtitles")
        try:
            sub = fetch_subtitles(url, MAX_SUMMARY_CHARS)
        except YtdlpError as exc:
            _update(job_id, status="failed", error=exc.message, stage=None)
            return
        except Exception as exc:
            logger.exception("subtitle fetch failed")
            _update(job_id, status="failed", error="获取字幕失败：{}".format(exc), stage=None)
            return

        cues = sub.get("cues") or []
        base_result = {
            "title": sub.get("title") or "未命名视频",
            "source": sub.get("source"),
            "language": sub.get("language"),
            "webpage_url": sub.get("webpage_url"),
            "cues": cues,
            "transcript": sub.get("transcript") or "",
            "overview": "",
            "outline": [],
            "highlights": [],
            "conclusion": "",
            "summary": "",
            "chapters": [],
            "mindmap": {"name": sub.get("title") or "视频", "children": []},
            "stream_markdown": "",
        }
        _update(
            job_id,
            status="running",
            stage="summarizing",
            transcript=sub.get("transcript") or "",
            result=base_result,
        )

        try:
            summary = summarize_transcript_streaming(
                sub["title"],
                sub["transcript"],
                on_delta=lambda delta: publish_delta(job_id, delta),
            )
        except YtdlpError as exc:
            _update(job_id, status="failed", error=exc.message, stage=None)
            return
        except Exception as exc:
            logger.exception("summarize failed")
            _update(job_id, status="failed", error="总结失败：{}".format(exc), stage=None)
            return

        mindmap = build_mindmap(
            summary.get("title") or sub["title"],
            summary.get("outline") or [],
            summary.get("highlights") or [],
        )
        result = {
            "title": summary.get("title") or sub["title"],
            "source": sub.get("source"),
            "language": sub.get("language"),
            "overview": summary.get("overview") or summary.get("summary") or "",
            "outline": summary.get("outline") or [],
            "highlights": summary.get("highlights") or [],
            "conclusion": summary.get("conclusion") or "",
            "summary": summary.get("summary") or summary.get("overview") or "",
            "chapters": summary.get("chapters") or [],
            "webpage_url": sub.get("webpage_url"),
            "cues": cues,
            "transcript": sub.get("transcript") or "",
            "mindmap": mindmap,
            "stream_markdown": summary.get("stream_markdown") or "",
        }
        _update(job_id, status="done", stage=None, result=result, error=None)
    finally:
        _summary_semaphore.release()
