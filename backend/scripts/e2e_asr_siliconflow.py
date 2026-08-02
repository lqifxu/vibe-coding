"""Minimal Douyin -> SiliconFlow ASR -> summarize E2E. ASCII-only logs, no keys."""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

DY_URL = os.environ.get(
    "TEST_DOUYIN_URL",
    "https://www.douyin.com/jingxuan?modal_id=7668087185878306067",
)
BASE = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8001")
HTTP_TIMEOUT = 60
POLL_SEC = 5
MAX_POLLS = 36  # each HTTP call <=60s; allow ~3min for download+ASR+LLM


def _out(msg: str) -> None:
    """ASCII-safe line (strip non-ascii)."""
    safe = re.sub(r"[^\x20-\x7E]", "?", str(msg))
    sys.stdout.buffer.write((safe + "\n").encode("ascii", "replace"))
    sys.stdout.buffer.flush()


def _mask(s: str) -> str:
    s = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", s or "")
    s = re.sub(r"(?i)(api[_-]?key|authorization)\s*[:=]\s*\S+", r"\1=***", s)
    return s


def _ascii_preview(text: str, n: int = 40) -> str:
    """Length + ascii-only preview (no CJK/emoji)."""
    raw = text or ""
    ascii_only = re.sub(r"[^\x20-\x7E]", "", raw)
    prev = ascii_only[:n]
    return "len={} ascii_preview={!r}".format(len(raw), prev)


def _http_json(method: str, url: str, body: dict | None = None, timeout: int = HTTP_TIMEOUT):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": _mask(raw[:200])}
        return e.code, payload
    except Exception as e:
        return 0, {"detail": _mask(str(e)[:200])}


def main() -> int:
    _out("STEP health")
    code, health = _http_json("GET", BASE + "/api/health")
    _out(
        "STATUS health http={} ok={} asr={} asr_api={} provider={}".format(
            code,
            health.get("ok"),
            health.get("asr"),
            health.get("asr_api"),
            health.get("asr_provider"),
        )
    )
    if code != 200 or not health.get("ok"):
        _out("FAIL health")
        return 1
    if not health.get("asr_api"):
        _out("FAIL asr_api_not_configured")
        return 2

    # Start summarize job (server does download -> ASR -> LLM)
    _out("STEP summarize_start")
    code, start = _http_json("POST", BASE + "/api/summarize", {"url": DY_URL})
    job_id = start.get("job_id") or ""
    detail = start.get("detail") or start.get("error") or ""
    _out(
        "STATUS summarize_start http={} job_id={} detail={}".format(
            code, job_id, _mask(str(detail)[:120])
        )
    )
    if code >= 400 or not job_id:
        _out("FAIL summarize_start")
        return 3

    final = None
    asr_nonempty = False
    summary_nonempty = False
    for i in range(MAX_POLLS):
        time.sleep(POLL_SEC)
        code2, st = _http_json("GET", BASE + "/api/summarize/" + job_id)
        status = st.get("status")
        stage = st.get("stage")
        err = st.get("error") or ""
        _out(
            "STATUS poll i={} http={} status={} stage={} err={}".format(
                i, code2, status, stage, _mask(str(err)[:100])
            )
        )
        if status in ("done", "failed", "error"):
            final = st
            break

    if not final:
        _out("FAIL poll_timeout job_id=" + job_id)
        return 4

    result = final.get("result") or {}
    transcript = str(result.get("transcript") or final.get("transcript") or "")
    if not transcript and isinstance(result.get("cues"), list):
        transcript = " ".join(
            str(c.get("text") or "") for c in result.get("cues") or []
        )

    # summary text fields used by frontend
    summary_text = ""
    for key in ("summary", "overview", "brief", "content"):
        v = result.get(key)
        if isinstance(v, str) and v.strip():
            summary_text = v
            break
    if not summary_text and isinstance(result.get("sections"), list):
        summary_text = " ".join(str(x) for x in result.get("sections") or [])
    if not summary_text:
        # any non-empty string field in result
        for v in result.values():
            if isinstance(v, str) and len(v.strip()) > 20:
                summary_text = v
                break

    asr_nonempty = bool(str(transcript).strip())
    summary_nonempty = bool(str(summary_text).strip()) and final.get("status") == "done"

    _out("STATUS final status=" + str(final.get("status")))
    _out("STATUS asr_nonempty={} {}".format(asr_nonempty, _ascii_preview(str(transcript))))
    _out(
        "STATUS summary_nonempty={} {}".format(
            summary_nonempty, _ascii_preview(str(summary_text))
        )
    )
    if final.get("status") != "done":
        _out(
            "FAIL summarize job_id={} http_err={} detail={}".format(
                job_id, final.get("status"), _mask(str(final.get("error") or "")[:160])
            )
        )
        return 5

    _out("RESULT job_id=" + job_id)
    _out("RESULT asr_nonempty=" + str(asr_nonempty))
    _out("RESULT summary_nonempty=" + str(summary_nonempty))
    if asr_nonempty and summary_nonempty:
        _out("RESULT OK")
        return 0
    _out("RESULT PARTIAL")
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
