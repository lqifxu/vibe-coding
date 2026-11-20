"""Cloud speech-to-text via OpenAI-compatible /audio/transcriptions.

Default provider is ``api`` (ASR_PROVIDER=api). Local faster-whisper is not
imported or initialized; it is only documented as a future optional provider.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import TEMP_DIR
from .cleanup import remove_dir
from .ytdlp_service import YtdlpError, get_ffmpeg_binary

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def asr_provider() -> str:
    """Configured provider. Default ``api``. ``local`` is reserved (not implemented)."""
    return (_env("ASR_PROVIDER", "api") or "api").lower()


def asr_api_configured() -> bool:
    return bool(_env("ASR_API_KEY"))


def asr_api_key() -> str:
    return _env("ASR_API_KEY")


def asr_base_url() -> str:
    return (_env("ASR_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


def asr_model() -> str:
    return _env("ASR_MODEL") or "whisper-1"


def asr_timeout_sec() -> float:
    try:
        return max(30.0, float(_env("ASR_TIMEOUT_SEC", "120") or "120"))
    except ValueError:
        return 120.0


def asr_max_duration_sec() -> int:
    try:
        return max(30, int(_env("ASR_MAX_DURATION_SEC", "1200") or "1200"))
    except ValueError:
        return 1200


def asr_available() -> bool:
    """True when cloud ASR can be used (ffmpeg + API key + provider=api)."""
    if not get_ffmpeg_binary():
        return False
    if asr_provider() != "api":
        return False
    return asr_api_configured()


def _require_cloud_asr() -> None:
    provider = asr_provider()
    if provider == "local":
        raise YtdlpError(
            "当前未启用本地 ASR。请将 ASR_PROVIDER=api 并配置云端 Whisper。",
            status_code=503,
        )
    if provider != "api":
        raise YtdlpError(
            "不支持的 ASR_PROVIDER={}，请使用 api。".format(provider),
            status_code=503,
        )
    if not asr_api_configured():
        raise YtdlpError(
            "未配置云端 ASR：请设置 ASR_API_KEY（及可选 ASR_BASE_URL / ASR_MODEL）。",
            status_code=503,
        )
    if not get_ffmpeg_binary():
        raise YtdlpError(
            "服务器未安装 ffmpeg，无法提取音频做语音转写。",
            status_code=503,
        )


def _format_ts(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "{:02d}:{:02d}:{:02d}".format(h, m, s)
    return "{:02d}:{:02d}".format(m, s)


def _probe_duration_sec(media: Path) -> Optional[float]:
    ffmpeg = get_ffmpeg_binary()
    if not ffmpeg:
        return None
    probe = Path(ffmpeg).with_name(
        "ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe"
    )
    bin_path = str(probe) if probe.exists() else ffmpeg
    try:
        if Path(bin_path).name.lower().startswith("ffprobe"):
            cmd = [
                bin_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media),
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            raw = (r.stdout or b"").decode("utf-8", "replace").strip()
            if raw:
                return float(raw)
            return None

        cmd = [ffmpeg, "-i", str(media)]
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        err = (r.stderr or b"").decode("utf-8", "replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
        if not m:
            return None
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mi * 60 + s
    except Exception as exc:
        logger.warning("probe duration failed: %s", exc)
        return None


def media_has_audio(media: Path) -> bool:
    """True when ffprobe/ffmpeg sees at least one audio stream."""
    ffmpeg = get_ffmpeg_binary()
    if not ffmpeg or not media.is_file():
        return False
    probe = Path(ffmpeg).with_name(
        "ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe"
    )
    try:
        if probe.exists():
            cmd = [
                str(probe),
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(media),
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            out = (r.stdout or b"").decode("utf-8", "replace").strip()
            return "audio" in out.lower()
        cmd = [ffmpeg, "-i", str(media)]
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        err = (r.stderr or b"").decode("utf-8", "replace").lower()
        return "audio:" in err or "stream #0:1" in err or "stream #0:0: audio" in err
    except Exception as exc:
        logger.warning("media_has_audio failed: %s", exc)
        return False


def extract_audio(
    media: Path,
    dest_dir: Optional[Path] = None,
    max_seconds: Optional[int] = None,
) -> Path:
    ffmpeg = get_ffmpeg_binary()
    if not ffmpeg:
        raise YtdlpError(
            "服务器未安装 ffmpeg，无法提取音频做语音转写。",
            status_code=503,
        )
    out_dir = dest_dir or (TEMP_DIR / str(uuid.uuid4()))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "audio.mp3"
    # Already-small audio files: remux/transcode; videos: drop video track.
    cmd = [ffmpeg, "-y", "-i", str(media)]
    if max_seconds and max_seconds > 0:
        cmd += ["-t", str(int(max_seconds))]
    cmd += [
        "-vn",
        "-map",
        "0:a:0?",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(out),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise YtdlpError("提取音频超时，请换更短的视频重试。", status_code=422) from exc
    stderr = (r.stderr or b"").decode("utf-8", "replace")
    if r.returncode != 0 or not out.is_file() or out.stat().st_size < 200:
        # Retry without optional map (older ffmpeg / odd containers).
        cmd2 = [ffmpeg, "-y", "-i", str(media)]
        if max_seconds and max_seconds > 0:
            cmd2 += ["-t", str(int(max_seconds))]
        cmd2 += ["-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(out)]
        try:
            r = subprocess.run(cmd2, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise YtdlpError("提取音频超时，请换更短的视频重试。", status_code=422) from exc
        stderr = (r.stderr or b"").decode("utf-8", "replace")
    if r.returncode != 0 or not out.is_file() or out.stat().st_size < 200:
        logger.warning("ffmpeg extract audio failed: %s", stderr[-400:])
        low = stderr.lower()
        if (
            "does not contain any stream" in low
            or "output file #0 does not contain any stream" in low
            or "matches no streams" in low
            or not media_has_audio(media)
        ):
            raise YtdlpError(
                "该视频文件没有音轨，无法语音转写。请换一条带人声的链接重试。",
                status_code=422,
            )
        raise YtdlpError("无法从视频中提取音频，请换一条链接重试。", status_code=422)
    return out


def _sanitize_asr_error(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"sk-[A-Za-z0-9_-]{10,}", "sk-***", text)
    text = re.sub(r"(?i)(api[_-]?key|authorization)\s*[:=]\s*\S+", r"\1=***", text)
    if len(text) > 200:
        text = text[:200] + "…"
    return text or "未知错误"


def _transcribe_api(audio: Path) -> Dict[str, Any]:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI

    client = OpenAI(
        api_key=asr_api_key(),
        base_url=asr_base_url(),
        timeout=asr_timeout_sec(),
    )
    model = asr_model()
    try:
        with open(audio, "rb") as f:
            try:
                resp = client.audio.transcriptions.create(
                    model=model,
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
            except Exception as first_exc:
                # Some gateways reject timestamp_granularities
                logger.info("ASR retry without timestamp_granularities: %s", first_exc)
                f.seek(0)
                resp = client.audio.transcriptions.create(
                    model=model,
                    file=f,
                    response_format="verbose_json",
                )
    except AuthenticationError as exc:
        raise YtdlpError(
            "云端 ASR 鉴权失败，请检查 ASR_API_KEY / ASR_BASE_URL。",
            status_code=503,
        ) from exc
    except APITimeoutError as exc:
        raise YtdlpError(
            "云端 ASR 请求超时，请稍后重试或换更短视频。",
            status_code=504,
        ) from exc
    except APIConnectionError as exc:
        raise YtdlpError(
            "无法连接云端 ASR 服务，请检查 ASR_BASE_URL 与服务器网络。",
            status_code=503,
        ) from exc
    except APIStatusError as exc:
        code = getattr(exc, "status_code", None) or 0
        detail = _sanitize_asr_error(str(getattr(exc, "message", None) or exc))
        if 400 <= int(code) < 500:
            raise YtdlpError(
                "云端 ASR 拒绝请求（HTTP {}）：{}".format(code, detail),
                status_code=422,
            ) from exc
        raise YtdlpError(
            "云端 ASR 服务异常（HTTP {}）：{}".format(code, detail),
            status_code=503,
        ) from exc
    except Exception as exc:
        raise YtdlpError(
            "云端 ASR 调用失败：{}".format(_sanitize_asr_error(str(exc))),
            status_code=503,
        ) from exc

    language = getattr(resp, "language", None) or "zh"
    segments = getattr(resp, "segments", None) or []
    cues: List[Dict[str, Any]] = []
    if segments:
        for seg in segments:
            if isinstance(seg, dict):
                text = str(seg.get("text") or "").strip()
                start = float(seg.get("start") or 0)
            else:
                text = str(getattr(seg, "text", "") or "").strip()
                start = float(getattr(seg, "start", 0) or 0)
            if not text:
                continue
            cues.append(
                {"start_sec": start, "start": _format_ts(start), "text": text}
            )
    if not cues:
        text = (getattr(resp, "text", None) or "").strip()
        if text:
            cues = [{"start_sec": 0.0, "start": "00:00", "text": text}]
    if not cues:
        raise YtdlpError(
            "语音转写结果为空（可能是静音或纯背景音乐）。",
            status_code=422,
        )
    return {"language": language, "cues": cues, "engine": "api:{}".format(model)}


def transcribe_media(media: Path) -> Dict[str, Any]:
    """Transcribe a local video/audio file into {language, cues, engine}."""
    _require_cloud_asr()
    if not media.is_file():
        raise YtdlpError("转写文件不存在", status_code=500)

    duration = _probe_duration_sec(media)
    max_dur = asr_max_duration_sec()
    truncate = None
    if duration and duration > max_dur:
        truncate = max_dur
        logger.info("ASR truncating media from %.0fs to %ss", duration, max_dur)

    work = TEMP_DIR / str(uuid.uuid4())
    work.mkdir(parents=True, exist_ok=True)
    try:
        audio = extract_audio(media, work, max_seconds=truncate)
        result = _transcribe_api(audio)
        if truncate and result.get("cues"):
            result["truncated"] = True
            result["cues"].append(
                {
                    "start_sec": float(truncate),
                    "start": _format_ts(float(truncate)),
                    "text": "（视频较长，仅转写前 {} 分钟）".format(
                        max(1, truncate // 60)
                    ),
                }
            )
        return result
    finally:
        remove_dir(work)
