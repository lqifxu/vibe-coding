"""Fetch platform captions, with speech-to-text when a site has no caption track."""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .asr_service import asr_available, transcribe_media
from .bilibili_service import is_bilibili_url
from .cleanup import remove_dir
from .config import TEMP_DIR
from .demo_fixture import demo_subtitles, is_demo_summary_url
from .douyin_service import download_douyin_for_asr, fetch_douyin_info, is_douyin_url
from .xiaohongshu_service import (
    download_xiaohongshu_for_asr,
    fetch_xiaohongshu_info,
    is_xiaohongshu_url,
)
from .ytdlp_service import YtdlpError, _base_opts

logger = logging.getLogger(__name__)

_LANG_PRIORITY = (
    "zh-Hans",
    "zh-CN",
    "ai-zh",
    "zh-Hant",
    "zh-TW",
    "zh",
    "en",
    "en-US",
    "en-GB",
    "ja",
    "ko",
)

_TIMESTAMP_LINE = re.compile(
    r"(?P<start>(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*"
    r"(?P<end>(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3})"
)
_VTT_TAG = re.compile(r"<[^>]+>")
_CUE_SETTINGS = re.compile(r"\s+(?:align|position|size|line|vertical):[^\s]+", re.I)


def _lang_rank(code: str) -> int:
    c = (code or "").strip()
    for i, pref in enumerate(_LANG_PRIORITY):
        if c == pref or c.lower().startswith(pref.lower()):
            return i
    return 1000


_CAPTION_EXT_RANK = {"json3": 0, "srv3": 1, "srt": 2, "ttml": 3, "vtt": 4}


def _caption_candidates(
    tracks: Dict[str, List[Dict[str, Any]]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """Original tracks first, then translations. json3 before playlist-style vtt."""
    found: List[Tuple[str, Dict[str, Any]]] = []
    for lang, items in (tracks or {}).items():
        for track in items or []:
            if not track.get("url"):
                continue
            protocol = (track.get("protocol") or "").lower()
            if protocol.startswith("m3u8"):
                continue
            ext = (track.get("ext") or "").lower()
            if ext and ext not in _CAPTION_EXT_RANK:
                continue
            found.append((lang, track))

    def sort_key(item: Tuple[str, Dict[str, Any]]) -> Tuple[int, int, int]:
        lang, track = item
        url = track.get("url") or ""
        translated = 1 if "tlang=" in url else 0
        ext_rank = _CAPTION_EXT_RANK.get((track.get("ext") or "").lower(), 9)
        return (translated, _lang_rank(lang), ext_rank)

    found.sort(key=sort_key)
    return found


def _pick_track(
    tracks: Dict[str, List[Dict[str, Any]]],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    candidates = _caption_candidates(tracks)
    if not candidates:
        return None
    return candidates[0]


def _parse_ts(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])


def _format_ts(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "{:02d}:{:02d}:{:02d}".format(h, m, s)
    return "{:02d}:{:02d}".format(m, s)


def parse_vtt_or_srt(raw: str) -> List[Dict[str, Any]]:
    """Parse WebVTT / SRT into [{start_sec, start, text}]."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    cues: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.upper().startswith("WEBVTT") or line.upper().startswith("NOTE"):
            continue
        if line.upper().startswith("STYLE") or line.upper().startswith("REGION"):
            while i < len(lines) and lines[i].strip():
                i += 1
            continue
        m = _TIMESTAMP_LINE.search(line)
        if not m:
            if i < len(lines):
                m2 = _TIMESTAMP_LINE.search(lines[i].strip())
                if m2:
                    m = m2
                    i += 1
                else:
                    continue
            else:
                continue
        start_sec = _parse_ts(m.group("start"))
        body: List[str] = []
        while i < len(lines) and lines[i].strip():
            body.append(lines[i].strip())
            i += 1
        cleaned = []
        for b in body:
            b = _VTT_TAG.sub("", b)
            b = _CUE_SETTINGS.sub("", b)
            b = (
                b.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
            )
            b = re.sub(r"\s+", " ", b).strip()
            if b:
                cleaned.append(b)
        if not cleaned:
            continue
        joined = " ".join(cleaned)
        if cues and cues[-1]["text"] == joined:
            continue
        cues.append(
            {
                "start_sec": start_sec,
                "start": _format_ts(start_sec),
                "text": joined,
            }
        )
    return cues


def _parse_json3(raw: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    events = data.get("events") or []
    cues: List[Dict[str, Any]] = []
    for ev in events:
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8") or "" for s in segs).replace("\n", " ").strip()
        if not text or text == "\n":
            continue
        start_ms = ev.get("tStartMs") or 0
        start_sec = float(start_ms) / 1000.0
        if cues and cues[-1]["text"] == text:
            continue
        cues.append(
            {
                "start_sec": start_sec,
                "start": _format_ts(start_sec),
                "text": text,
            }
        )
    return cues


def _cues_from_track(track: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = _download_url(track.get("url") or "")
    if raw.lstrip().startswith("#EXTM3U"):
        return []
    ext = (track.get("ext") or "").lower()
    if ext == "json3" or raw.lstrip().startswith("{"):
        return _parse_json3(raw)
    return parse_vtt_or_srt(raw)


def cues_to_transcript(cues: List[Dict[str, Any]], max_chars: int) -> str:
    lines = ["[{}] {}".format(c["start"], c["text"]) for c in cues]
    out = "\n".join(lines)
    if len(out) <= max_chars:
        return out
    kept: List[str] = []
    total = 0
    for line in lines:
        if total + len(line) + 1 > max_chars:
            break
        kept.append(line)
        total += len(line) + 1
    return "\n".join(kept) + "\n…（字幕过长，已截断）"


def _format_subtitle_ts(sec: float, ms_sep: str = ",") -> str:
    """HH:MM:SS{sep}mmm for SRT (,) or VTT (.)."""
    total_ms = max(0, int(round(float(sec) * 1000)))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "{:02d}:{:02d}:{:02d}{}{:03d}".format(h, m, s, ms_sep, ms)


def _cue_end_sec(cues: List[Dict[str, Any]], index: int) -> float:
    start = float(cues[index].get("start_sec") or 0)
    if index + 1 < len(cues):
        nxt = float(cues[index + 1].get("start_sec") or start)
        if nxt > start:
            return nxt
    return start + 2.0


def cues_to_srt(cues: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for i, c in enumerate(cues):
        start = _format_subtitle_ts(float(c.get("start_sec") or 0), ",")
        end = _format_subtitle_ts(_cue_end_sec(cues, i), ",")
        text = (c.get("text") or "").strip()
        blocks.append("{}\n{} --> {}\n{}\n".format(i + 1, start, end, text))
    return "\n".join(blocks)


def cues_to_vtt(cues: List[Dict[str, Any]]) -> str:
    blocks: List[str] = ["WEBVTT", ""]
    for i, c in enumerate(cues):
        start = _format_subtitle_ts(float(c.get("start_sec") or 0), ".")
        end = _format_subtitle_ts(_cue_end_sec(cues, i), ".")
        text = (c.get("text") or "").strip()
        blocks.append("{} --> {}\n{}\n".format(start, end, text))
    return "\n".join(blocks)


def export_subtitles(
    cues: List[Dict[str, Any]],
    fmt: str,
    transcript: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Return (body, media_type, extension) for fmt in srt|vtt|txt.
    """
    key = (fmt or "srt").strip().lower()
    if key == "vtt":
        return cues_to_vtt(cues), "text/vtt; charset=utf-8", "vtt"
    if key == "txt":
        body = (transcript or "").strip() or cues_to_transcript(cues, 10**9)
        return body, "text/plain; charset=utf-8", "txt"
    if key != "srt":
        raise YtdlpError("不支持的字幕格式，请使用 srt / vtt / txt。", status_code=400)
    return cues_to_srt(cues), "application/x-subrip; charset=utf-8", "srt"


def _bili_cookie_header() -> str:
    """Optional login cookie so Bilibili returns CC when need_login_subtitle=true."""
    raw = (
        os.getenv("BILI_COOKIE", "").strip()
        or os.getenv("BILIBILI_COOKIE", "").strip()
    )
    if raw:
        return raw
    sess = os.getenv("SESSDATA", "").strip()
    if not sess:
        return ""
    if sess.lower().startswith("sessdata="):
        return sess
    return "SESSDATA={}".format(sess)


def _download_url(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "youtube.com" in host or "googlevideo.com" in host:
        referer = "https://www.youtube.com/"
    elif "bilibili.com" in host or "hdslb.com" in host:
        referer = "https://www.bilibili.com/"
    else:
        referer = "https://{}/".format(host) if host else "https://www.youtube.com/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
    }
    cookie = _bili_cookie_header()
    if cookie and ("bilibili.com" in host or "hdslb.com" in host):
        headers["Cookie"] = cookie
    req = Request(url, headers=headers)
    with urlopen(req, timeout=45) as resp:
        data = resp.read()
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")



def _parse_bilibili_json(raw: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    body = data.get("body") or []
    cues: List[Dict[str, Any]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or "").strip()
        if not text:
            continue
        start_sec = float(item.get("from") or 0)
        if cues and cues[-1]["text"] == text:
            continue
        cues.append(
            {
                "start_sec": start_sec,
                "start": _format_ts(start_sec),
                "text": text,
            }
        )
    return cues


def _fetch_bilibili_subtitles(url: str) -> Optional[Dict[str, Any]]:
    """Fallback: Bilibili open API when yt-dlp reports no captions.

    player/v2 often sets need_login_subtitle and returns empty tracks.
    x/v2/dm/view still exposes AI auto captions (ai-zh) without login.
    """
    m = re.search(r"(BV[\w]+)", url, re.I)
    if not m:
        return None
    bvid = m.group(1)
    try:
        view_raw = _download_url(
            "https://api.bilibili.com/x/web-interface/view?bvid={}".format(bvid)
        )
        view = json.loads(view_raw)
        if view.get("code") != 0:
            return None
        data = view.get("data") or {}
        cid = data.get("cid")
        aid = data.get("aid")
        title = data.get("title") or "未命名视频"
        if not cid or not aid:
            return None

        tracks: List[Dict[str, Any]] = []
        # Prefer dm/view first: exposes AI auto captions without login.
        # player/v2 often returns empty when need_login_subtitle=true.
        for api_url in (
            "https://api.bilibili.com/x/v2/dm/view?aid={}&oid={}&type=1".format(aid, cid),
            "https://api.bilibili.com/x/player/v2?aid={}&cid={}".format(aid, cid),
        ):
            try:
                raw = _download_url(api_url)
                payload = json.loads(raw)
                found = (
                    ((payload.get("data") or {}).get("subtitle") or {}).get("subtitles")
                    or []
                )
                if found:
                    tracks = found
                    break
            except Exception as exc:
                logger.warning("bilibili subtitle api failed (%s): %s", api_url, exc)

        if not tracks:
            return None

        tracks = sorted(
            tracks,
            key=lambda t: _lang_rank(str(t.get("lan") or "")),
        )
        track = tracks[0]
        sub_url = track.get("subtitle_url") or ""
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        elif sub_url.startswith("http://"):
            sub_url = "https://" + sub_url[len("http://") :]
        if not sub_url:
            return None
        raw = _download_url(sub_url)
        cues = _parse_bilibili_json(raw)
        if not cues:
            return None
        lan = str(track.get("lan") or "zh")
        source = "auto" if lan.startswith("ai-") or "自动" in str(track.get("lan_doc") or "") else "manual"
        return {
            "title": title,
            "language": lan,
            "source": source,
            "cues": cues,
            "webpage_url": "https://www.bilibili.com/video/{}".format(bvid),
        }
    except Exception as exc:
        logger.warning("bilibili subtitle fallback failed: %s", exc)
        return None


def _pack_bilibili_subtitles(url: str, max_chars: int) -> Optional[Dict[str, Any]]:
    bili = _fetch_bilibili_subtitles(url)
    if not bili:
        return None
    transcript = cues_to_transcript(bili["cues"], max_chars)
    return {
        "title": bili["title"],
        "language": bili["language"],
        "source": bili["source"],
        "cues": bili["cues"],
        "transcript": transcript,
        "webpage_url": bili.get("webpage_url") or url,
    }


def _subtitles_from_media(
    info: Dict[str, Any],
    media,
    max_chars: int,
    url: str,
    fallback_title: str,
) -> Dict[str, Any]:
    job_dir = media.parent
    try:
        asr = transcribe_media(media)
    finally:
        remove_dir(job_dir)
    cues = asr.get("cues") or []
    if not cues:
        raise YtdlpError("语音转写结果为空，无法生成总结。", status_code=422)
    return {
        "title": info.get("title") or fallback_title,
        "language": asr.get("language") or "zh",
        "source": "asr",
        "cues": cues,
        "transcript": cues_to_transcript(cues, max_chars),
        "webpage_url": info.get("webpage_url") or url,
        "asr_engine": asr.get("engine"),
    }


def _fetch_douyin_subtitles_via_asr(url: str, max_chars: int) -> Dict[str, Any]:
    """Download Douyin media and speech-to-text (no official caption track)."""
    if not asr_available():
        raise YtdlpError(
            "抖音无字幕轨，需要云端语音转写才能总结。"
            "未配置云端 ASR：请设置 ASR_PROVIDER=api 与 ASR_API_KEY。",
            status_code=503,
        )
    info = fetch_douyin_info(url)
    media = download_douyin_for_asr(url)
    return _subtitles_from_media(info, media, max_chars, url, "抖音视频")


def _is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "youtu.be" or host.endswith("youtube.com") or host.endswith("youtube-nocookie.com")


def _download_youtube_audio(url: str) -> Path:
    """Lowest audio track is enough for speech-to-text."""
    job_dir = TEMP_DIR / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=True)
    opts = _base_opts(url)
    opts.update(
        {
            "format": "worstaudio/bestaudio/worst",
            "outtmpl": str(job_dir / "audio.%(ext)s"),
            "noplaylist": True,
            "max_filesize": 80 * 1024 * 1024,
        }
    )
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except (DownloadError, ExtractorError) as exc:
        remove_dir(job_dir)
        logger.warning("youtube audio download failed: %s", exc)
        raise YtdlpError("下载音频失败，暂时无法转写这条 YouTube 视频。", status_code=422) from exc
    except Exception as exc:
        remove_dir(job_dir)
        logger.exception("youtube audio download error")
        raise YtdlpError("下载音频失败：{}".format(exc), status_code=500) from exc

    files = [
        p
        for p in job_dir.iterdir()
        if p.is_file() and p.suffix.lower() not in {".json", ".part", ".ytdl", ".temp"}
    ]
    if not files:
        remove_dir(job_dir)
        raise YtdlpError("没有下载到音频，暂时无法转写这条 YouTube 视频。", status_code=422)
    return max(files, key=lambda p: p.stat().st_size)


def _fetch_youtube_subtitles_via_asr(
    url: str,
    max_chars: int,
    info: Dict[str, Any],
) -> Dict[str, Any]:
    if not asr_available():
        raise YtdlpError(
            "这条 YouTube 视频没有字幕轨，需要云端语音转写才能生成字幕。"
            "未配置云端 ASR：请设置 ASR_PROVIDER=api 与 ASR_API_KEY。",
            status_code=503,
        )
    media = _download_youtube_audio(url)
    return _subtitles_from_media(info, media, max_chars, url, info.get("title") or "YouTube 视频")


def _fetch_xiaohongshu_subtitles_via_asr(url: str, max_chars: int) -> Dict[str, Any]:
    """Xiaohongshu notes have no caption file; transcribe the video instead."""
    if not asr_available():
        raise YtdlpError(
            "小红书笔记没有独立字幕轨，需要云端语音转写才能生成字幕。"
            "未配置云端 ASR：请设置 ASR_PROVIDER=api 与 ASR_API_KEY。",
            status_code=503,
        )
    info = fetch_xiaohongshu_info(url)
    media = download_xiaohongshu_for_asr(url)
    return _subtitles_from_media(info, media, max_chars, url, "小红书笔记")


def fetch_subtitles(url: str, max_chars: int) -> Dict[str, Any]:
    """Return title / language / source / cues / transcript for a video URL."""
    if is_demo_summary_url(url):
        return demo_subtitles(max_chars)
    if is_douyin_url(url):
        return _fetch_douyin_subtitles_via_asr(url, max_chars)
    if is_xiaohongshu_url(url):
        return _fetch_xiaohongshu_subtitles_via_asr(url, max_chars)

    # B站：云服务器访问网页常 412，直接走公开字幕 API（含 AI 字幕）
    if is_bilibili_url(url):
        packed = _pack_bilibili_subtitles(url, max_chars)
        if packed:
            return packed
        raise YtdlpError(
            "该 B站视频没有可用字幕（含 AI 字幕）。当前不对 B站做整片语音转写。",
            status_code=422,
        )

    opts = _base_opts(url)
    opts.update(
        {
            "skip_download": True,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "listsubtitles": False,
        }
    )
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except (DownloadError, ExtractorError) as exc:
        logger.warning("subtitle extract_info failed: %s", exc)
        packed = _pack_bilibili_subtitles(url, max_chars)
        if packed:
            return packed
        raise YtdlpError("无法解析视频以获取字幕，请检查链接是否有效。", status_code=422)
    except Exception as exc:
        logger.exception("unexpected subtitle extract error")
        raise YtdlpError("获取字幕失败：{}".format(exc), status_code=500)

    if not info:
        raise YtdlpError("未获取到视频信息", status_code=422)

    if info.get("_type") == "playlist" and info.get("entries"):
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise YtdlpError("播放列表为空", status_code=422)
        info = entries[0]

    title = info.get("title") or "未命名视频"
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    attempts = [("manual", manual), ("auto", auto)]
    last_error = ""
    for source, tracks in attempts:
        for lang, track in _caption_candidates(tracks):
            try:
                cues = _cues_from_track(track)
            except Exception as exc:
                last_error = str(exc)
                logger.warning("download subtitle failed (%s %s): %s", source, lang, exc)
                continue
            if not cues:
                continue
            transcript = cues_to_transcript(cues, max_chars)
            return {
                "title": title,
                "language": lang,
                "source": source,
                "cues": cues,
                "transcript": transcript,
                "webpage_url": info.get("webpage_url") or url,
            }

    packed = _pack_bilibili_subtitles(url, max_chars)
    if packed:
        return packed
    if _is_youtube_url(url):
        return _fetch_youtube_subtitles_via_asr(url, max_chars, info)
    if last_error:
        raise YtdlpError("下载字幕失败，请稍后重试。", status_code=502)
    raise YtdlpError(
        "该视频没有可用字幕。v1 仅支持已有字幕/自动字幕的视频，暂不提供语音转写。",
        status_code=422,
    )
