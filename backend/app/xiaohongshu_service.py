"""Xiaohongshu note resolver.

yt-dlp has no Xiaohongshu extractor. The note page only returns video URLs to a
browser-like TLS client; plain urllib is redirected to the login wall.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import MAX_DOWNLOAD_BYTES, TEMP_DIR
from .cleanup import remove_dir

logger = logging.getLogger(__name__)

_NOTE_ID_RE = re.compile(r"(?:explore|discovery/item|item)/(?P<id>[0-9a-f]{16,32})", re.I)
_PROFILE_NOTE_RE = re.compile(r"/user/profile/[^/]+/(?P<id>[0-9a-f]{16,32})", re.I)


class XiaohongshuError(Exception):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_xiaohongshu_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(
        host == name or host.endswith("." + name)
        for name in ("xiaohongshu.com", "xhslink.com", "xhs.cn")
    )


def _session():
    try:
        from curl_cffi import requests
    except ImportError as exc:
        raise XiaohongshuError(
            "缺少 curl_cffi，无法模拟浏览器访问小红书。请在 backend 执行 pip install curl_cffi。",
            status_code=500,
        ) from exc
    return requests.Session(impersonate="chrome131")


def _format_size(n: Optional[int]) -> Optional[str]:
    if not n or n <= 0:
        return None
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return "{} {}".format(int(size), unit)
            return "{:.1f} {}".format(size, unit)
        size /= 1024
    return None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _loads_state(html: str) -> Dict[str, Any]:
    marker = "window.__INITIAL_STATE__="
    idx = html.find(marker)
    if idx < 0:
        marker = "window.__INITIAL_STATE__ ="
        idx = html.find(marker)
    if idx < 0:
        raise XiaohongshuError("没有读到笔记数据。请粘贴带 xsec_token 的分享链接。")
    blob = html[idx + len(marker) :].lstrip()
    if blob.startswith("%"):
        blob = urllib.parse.unquote(blob)
    blob = re.sub(r"\bundefined\b", "null", blob)
    try:
        data, _ = json.JSONDecoder().raw_decode(blob)
    except json.JSONDecodeError as exc:
        raise XiaohongshuError("笔记数据无法解析，链接可能已失效。") from exc
    if not isinstance(data, dict):
        raise XiaohongshuError("笔记数据无法解析，链接可能已失效。")
    return data


def _note_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    detail = (state.get("note") or {}).get("noteDetailMap") or {}
    if not isinstance(detail, dict):
        detail = {}
    for key, val in detail.items():
        if key in ("undefined", "null") or not isinstance(val, dict):
            continue
        note = val.get("note") if isinstance(val.get("note"), dict) else val
        if isinstance(note, dict) and (note.get("noteId") or note.get("type") or note.get("desc")):
            return note
    raise XiaohongshuError("未找到笔记内容。请使用「分享 → 复制链接」里的完整地址。")


def _stream_urls(item: Dict[str, Any]) -> List[str]:
    master = item.get("masterUrl") or item.get("url")
    urls: List[str] = []
    if isinstance(master, str) and master.startswith("http"):
        urls.append(master)
    for extra in item.get("backupUrls") or []:
        if isinstance(extra, str) and extra.startswith("http") and extra not in urls:
            urls.append(extra)
    return urls


def _streams(note: Dict[str, Any]) -> List[Dict[str, Any]]:
    video = note.get("video") if isinstance(note.get("video"), dict) else {}
    media = video.get("media") if isinstance(video.get("media"), dict) else {}
    stream = media.get("stream") if isinstance(media.get("stream"), dict) else {}
    found: List[Dict[str, Any]] = []
    for codec, items in stream.items():
        if not isinstance(items, list):
            continue
        codec_l = str(codec).lower()
        # Separate audio track list — used for ASR when video stream is silent.
        if codec_l in ("audio", "aac", "mp4a"):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            urls = _stream_urls(item)
            if not urls:
                continue
            width = _as_int(item.get("width"))
            height = _as_int(item.get("height"))
            short = min(width, height) if width and height else (height or width)
            duration_ms = 0
            for key in ("duration", "audioDuration", "videoDuration"):
                val = _as_int(item.get(key))
                if val > 1000:
                    duration_ms = val
                    break
            audio_codec = str(item.get("audioCodec") or item.get("audio_codec") or "").lower()
            has_audio = bool(audio_codec) and audio_codec not in ("none", "null", "unknown")
            found.append(
                {
                    "codec": codec_l,
                    "short": short,
                    "height": height or None,
                    "size": _as_int(item.get("size")) or None,
                    "duration_ms": duration_ms,
                    "has_audio": has_audio,
                    "urls": urls,
                }
            )
    return found


def _audio_urls_from_note(note: Dict[str, Any]) -> List[str]:
    """Collect dedicated audio CDN URLs when video masterUrl has no soundtrack."""
    video = note.get("video") if isinstance(note.get("video"), dict) else {}
    media = video.get("media") if isinstance(video.get("media"), dict) else {}
    stream = media.get("stream") if isinstance(media.get("stream"), dict) else {}
    urls: List[str] = []
    for key in ("audio", "aac", "mp4a"):
        items = stream.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for u in _stream_urls(item):
                if u not in urls:
                    urls.append(u)
    # Some notes expose audio under video.consumer or music-like fields.
    for key in ("audioUrl", "soundUrl", "mp3Url"):
        raw = video.get(key) or media.get(key)
        if isinstance(raw, str) and raw.startswith("http") and raw not in urls:
            urls.append(raw)
    return urls


def _meta_from_note(note: Dict[str, Any], page_url: str) -> Dict[str, Any]:
    streams = _streams(note)
    if not streams:
        images = note.get("imageList") or []
        if images:
            raise XiaohongshuError("这是图文笔记，当前只支持下载视频笔记。")
        raise XiaohongshuError("已打开笔记，但没有可下载的视频地址。")

    codec_rank = {"h264": 0, "av1": 1, "h265": 2, "h266": 3}
    best: Dict[int, Dict[str, Any]] = {}
    for stream in streams:
        key = stream["short"] or stream["size"] or len(best)
        prev = best.get(key)
        rank = codec_rank.get(stream["codec"], 9)
        prev_rank = codec_rank.get(prev["codec"], 9) if prev else 99
        # Prefer streams that declare an audio codec (needed for ASR / playback with sound).
        better_audio = bool(stream.get("has_audio")) and not (prev or {}).get("has_audio")
        worse_audio = not stream.get("has_audio") and bool((prev or {}).get("has_audio"))
        if worse_audio:
            continue
        if prev is None or better_audio or rank < prev_rank or (
            rank == prev_rank and (stream["size"] or 0) > (prev["size"] or 0)
        ):
            best[key] = stream
    ordered = sorted(
        best.values(),
        key=lambda s: (1 if s.get("has_audio") else 0, s["short"], s["size"] or 0),
        reverse=True,
    )

    formats: List[Dict[str, Any]] = []
    play_map: Dict[str, List[str]] = {}
    duration_ms = 0
    for stream in ordered:
        short = stream["short"] or 0
        fid = "xhs-{}".format(short) if short else "xhs-video"
        if fid in play_map:
            continue
        size = stream["size"]
        formats.append(
            {
                "format_id": fid,
                "label": "{}p".format(short) if short else "视频",
                "ext": "mp4",
                "height": stream["height"],
                "has_audio": True,
                "filesize": size,
                "filesize_text": _format_size(size),
                "note": "小红书直链",
            }
        )
        play_map[fid] = stream["urls"]
        if not duration_ms and stream["duration_ms"]:
            duration_ms = stream["duration_ms"]
    if formats and "xhs-video" not in play_map:
        play_map["xhs-video"] = play_map[formats[0]["format_id"]]

    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    title = (note.get("title") or note.get("desc") or "").strip() or "小红书笔记"
    cover = None
    images = note.get("imageList") or []
    if images and isinstance(images[0], dict):
        cover = images[0].get("urlDefault") or images[0].get("url")
    note_id = str(note.get("noteId") or _note_id(page_url) or "")
    if duration_ms > 1000:
        duration = int(duration_ms / 1000)
    else:
        duration = duration_ms or None
    return {
        "id": note_id,
        "title": title,
        "uploader": user.get("nickname"),
        "thumbnail": cover,
        "duration": duration,
        "formats": formats,
        "play_map": play_map,
        "audio_urls": _audio_urls_from_note(note),
        "webpage_url": page_url,
    }


def _note_id(url: str) -> Optional[str]:
    match = _NOTE_ID_RE.search(url) or _PROFILE_NOTE_RE.search(url)
    return match.group("id") if match else None


def _friendly_page_error(final_url: str) -> Optional[str]:
    try:
        parsed = urllib.parse.urlparse(final_url)
        qs = urllib.parse.parse_qs(parsed.query)
    except Exception:
        return None
    path = parsed.path or ""
    if path.startswith("/login"):
        return "小红书要求登录后才能查看这条笔记。请换一条公开分享链接。"
    code = (qs.get("error_code") or [""])[0]
    msg = (qs.get("error_msg") or [""])[0]
    if code == "300031" or "无法浏览" in msg or "Isn't Available" in msg:
        return "这条小红书笔记暂时无法浏览，可能已删除或限制访问。"
    if "/404" in path:
        return "没有打开小红书笔记页。请粘贴完整分享链接（需包含 xsec_token）。"
    return None


def _fetch_html(url: str) -> tuple:
    session = _session()
    # Guest cookies from the explore page are required before a note request.
    try:
        session.get(
            "https://www.xiaohongshu.com/explore",
            timeout=20,
            allow_redirects=True,
            headers={"Referer": "https://www.xiaohongshu.com/"},
        )
    except Exception as exc:
        logger.warning("xhs warmup failed: %s", exc)
    try:
        resp = session.get(
            url,
            timeout=25,
            allow_redirects=True,
            headers={"Referer": "https://www.xiaohongshu.com/"},
        )
    except Exception as exc:
        raise XiaohongshuError("请求小红书失败：{}".format(exc)) from exc
    final_url = str(resp.url)
    err = _friendly_page_error(final_url)
    if err:
        raise XiaohongshuError(err)
    if resp.status_code != 200:
        raise XiaohongshuError("请求小红书失败：HTTP {}".format(resp.status_code))
    return final_url, resp.text or ""


def fetch_xiaohongshu_info(url: str) -> Dict[str, Any]:
    final_url, html = _fetch_html(url)
    if "masterUrl" not in html and "imageList" not in html and "noteDetailMap" not in html:
        err = _friendly_page_error(final_url)
        raise XiaohongshuError(err or "没有读到笔记内容。请粘贴完整分享链接。")
    note = _note_from_state(_loads_state(html))
    meta = _meta_from_note(note, final_url if _note_id(final_url) else url)
    play_map = meta.pop("play_map")
    audio_urls = list(meta.pop("audio_urls", None) or [])
    flat: List[str] = []
    for urls in play_map.values():
        for item in urls:
            if item not in flat:
                flat.append(item)
    return {
        "id": meta["id"],
        "title": meta["title"],
        "thumbnail": meta.get("thumbnail"),
        "duration": meta.get("duration"),
        "extractor": "Xiaohongshu",
        "uploader": meta.get("uploader"),
        "webpage_url": meta.get("webpage_url") or url,
        "formats": meta.get("formats") or [],
        "_xhs_play_map": play_map,
        "_xhs_play_urls": flat,
        "_xhs_audio_urls": audio_urls,
    }


def _download_xhs_urls(
    session,
    urls: List[str],
    out_path: Path,
    min_bytes: int = 1000,
) -> Path:
    last_err = None
    for play in urls:
        try:
            resp = session.get(
                play,
                timeout=60,
                allow_redirects=True,
                headers={"Referer": "https://www.xiaohongshu.com/"},
                stream=True,
            )
            if resp.status_code != 200:
                raise XiaohongshuError("下载失败：HTTP {}".format(resp.status_code))
            total = 0
            with open(out_path, "wb") as handle:
                for chunk in resp.iter_content(1024 * 256):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise XiaohongshuError("文件超过体积上限（500MB）", status_code=413)
                    handle.write(chunk)
            if total < min_bytes:
                raise XiaohongshuError("下载内容过小，可能不是媒体文件")
            logger.info("xhs downloaded %s bytes", total)
            return out_path
        except XiaohongshuError:
            raise
        except Exception as exc:
            last_err = exc
            logger.warning("xhs media url failed: %s", exc)
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            continue
    raise XiaohongshuError("小红书媒体下载失败：{}".format(last_err or "无可用直链"))


def download_xiaohongshu(
    url: str,
    dest_dir: Optional[Path] = None,
    format_id: Optional[str] = None,
) -> Path:
    info = fetch_xiaohongshu_info(url)
    play_map = info.get("_xhs_play_map") or {}
    fid = (format_id or "").strip()
    play_urls = list(play_map.get(fid) or [])
    if not play_urls:
        play_urls = list(play_map.get("xhs-video") or [])
    if not play_urls:
        play_urls = list(info.get("_xhs_play_urls") or [])
    if not play_urls:
        raise XiaohongshuError("没有可下载的视频地址")

    session = _session()
    job_dir = dest_dir or (TEMP_DIR / str(uuid.uuid4()))
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", info["title"])[:60] or info["id"]
    out_path = job_dir / "{} [{}].mp4".format(safe_title, info["id"])

    try:
        return _download_xhs_urls(session, play_urls, out_path)
    except XiaohongshuError:
        remove_dir(job_dir)
        raise


def download_xiaohongshu_for_asr(url: str, dest_dir: Optional[Path] = None) -> Path:
    """Prefer dedicated audio CDN when video masterUrl is silent."""
    info = fetch_xiaohongshu_info(url)
    session = _session()
    job_dir = dest_dir or (TEMP_DIR / str(uuid.uuid4()))
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", info["title"])[:60] or info["id"]

    audio_urls = list(info.get("_xhs_audio_urls") or [])
    if audio_urls:
        out_path = job_dir / "{} [{}].m4a".format(safe_title, info["id"])
        try:
            return _download_xhs_urls(session, audio_urls, out_path, min_bytes=500)
        except XiaohongshuError as exc:
            logger.warning("xhs audio download failed, try video: %s", exc)
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass

    play_map = info.get("_xhs_play_map") or {}
    play_urls = list(play_map.get("xhs-video") or []) or list(
        info.get("_xhs_play_urls") or []
    )
    out_path = job_dir / "{} [{}].mp4".format(safe_title, info["id"])
    try:
        return _download_xhs_urls(session, play_urls, out_path)
    except XiaohongshuError:
        remove_dir(job_dir)
        raise

