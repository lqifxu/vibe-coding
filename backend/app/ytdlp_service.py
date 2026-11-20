"""Thin wrapper around yt-dlp YoutubeDL."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .config import BASE_DIR, FFMPEG_DIR, MAX_DOWNLOAD_BYTES, TEMP_DIR
from .cleanup import remove_dir
from .demo_fixture import demo_video_info, is_demo_summary_url
from .bilibili_service import (
    BilibiliError,
    download_bilibili,
    fetch_bilibili_info,
    is_bilibili_url,
)
from .douyin_service import (
    DouyinError,
    download_douyin,
    fetch_douyin_info,
    is_douyin_url,
)
from .xiaohongshu_service import (
    XiaohongshuError,
    download_xiaohongshu,
    fetch_xiaohongshu_info,
    is_xiaohongshu_url,
)

logger = logging.getLogger(__name__)

# Prefer short-link / platform domains when multiple URLs appear in share text
_PREFERRED_HOST_HINTS = (
    "v.douyin.com",
    "www.douyin.com",
    "www.iesdouyin.com",
    "douyin.com",
    "v.tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "b23.tv",
    "bilibili.com",
    "youtu.be",
    "youtube.com",
    "xiaohongshu.com",
    "xhslink.com",
    "instagram.com",
    "twitter.com",
    "x.com",
)

_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAIL_PUNCT_RE = re.compile(r"[)\],.，。！？；：、》〉」』】]+$")

_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


class YtdlpError(Exception):
    def __init__(self, message, status_code=400):
        super(YtdlpError, self).__init__(message)
        self.message = message
        self.status_code = status_code


def _bili_cookie_header() -> str:
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


def _cookiefile_path() -> Optional[str]:
    """Optional Netscape cookies.txt for yt-dlp (all platforms)."""
    env = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    if env and Path(env).is_file():
        return env
    for name in ("cookies.txt", "bilibili_cookies.txt"):
        cand = BASE_DIR / name
        if cand.is_file():
            return str(cand)
    return None


def _base_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": {
            "User-Agent": _DESKTOP_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.bilibili.com/",
        },
    }
    ffdir = get_ffmpeg_dir()
    if ffdir:
        opts["ffmpeg_location"] = ffdir
    cookiefile = _cookiefile_path()
    if cookiefile:
        opts["cookiefile"] = cookiefile
    bili_cookie = _bili_cookie_header()
    if bili_cookie:
        opts["http_headers"]["Cookie"] = bili_cookie
    node = shutil.which("node")
    if node:
        opts["js_runtimes"] = {"node": {"path": str(Path(node).resolve().parent)}}
    return opts


def get_ffmpeg_dir():
    if FFMPEG_DIR:
        return FFMPEG_DIR
    which = shutil.which("ffmpeg")
    if which:
        return str(Path(which).resolve().parent)
    return None


def get_ffmpeg_binary():
    d = get_ffmpeg_dir()
    if not d:
        return None
    for name in ("ffmpeg.exe", "ffmpeg"):
        cand = Path(d) / name
        if cand.exists():
            return str(cand)
    return None


def ffmpeg_available():
    return get_ffmpeg_binary() is not None


def ytdlp_version():
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:
        return "unknown"


def _format_size(n):
    if not n or n <= 0:
        return None
    units = ["B", "KB", "MB", "GB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            if u == "B":
                return "{} {}".format(int(size), u)
            return "{:.1f} {}".format(size, u)
        size /= 1024
    return None


def _height_label(height):
    if not height:
        return "未知"
    if height >= 2160:
        return "4K"
    if height >= 1440:
        return "1440p"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    if height >= 480:
        return "480p"
    if height >= 360:
        return "360p"
    return "{}p".format(height)


def _pick_formats(info):
    raw = info.get("formats") or []
    seen = set()
    result = []
    has_ffmpeg = ffmpeg_available()

    candidates = []
    for f in raw:
        if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none"):
            candidates.append(("audio", f))
        elif f.get("vcodec") not in (None, "none"):
            candidates.append(("video", f))

    videos = [f for kind, f in candidates if kind == "video"]
    videos.sort(
        key=lambda x: (
            1 if x.get("acodec") not in (None, "none") else 0,
            x.get("height") or 0,
            x.get("tbr") or 0,
        ),
        reverse=True,
    )

    for f in videos:
        height = f.get("height")
        ext = f.get("ext") or "mp4"
        fid = f.get("format_id")
        if not fid:
            continue
        has_audio = f.get("acodec") not in (None, "none")
        key = (height, ext, has_audio)
        if key in seen:
            continue
        seen.add(key)

        filesize = f.get("filesize") or f.get("filesize_approx")
        if filesize and filesize > MAX_DOWNLOAD_BYTES:
            continue

        label = _height_label(height)
        note_parts = []
        if has_audio:
            format_id = fid
        elif has_ffmpeg:
            format_id = "{}+bestaudio/best".format(fid)
            note_parts.append("需合并音轨")
        else:
            format_id = fid
            label = "{} · 仅画面".format(label)
            note_parts.append("无声（未安装 ffmpeg，无法合并音轨）")
        result.append({
            "format_id": format_id,
            "label": label,
            "ext": ext,
            "height": height,
            "has_audio": has_audio,
            "filesize": filesize,
            "filesize_text": _format_size(filesize),
            "note": " · ".join(note_parts) if note_parts else None,
        })
        if len(result) >= 8:
            break

    audios = [f for kind, f in candidates if kind == "audio"]
    audios.sort(key=lambda x: x.get("abr") or x.get("tbr") or 0, reverse=True)
    if audios:
        a = audios[0]
        filesize = a.get("filesize") or a.get("filesize_approx")
        result.append({
            "format_id": a.get("format_id"),
            "label": "仅音频",
            "ext": a.get("ext") or "m4a",
            "height": None,
            "has_audio": True,
            "filesize": filesize,
            "filesize_text": _format_size(filesize),
            "note": "音频文件",
        })

    if not result:
        result.append({
            "format_id": "best",
            "label": "最佳质量",
            "ext": info.get("ext") or "mp4",
            "height": info.get("height"),
            "has_audio": True,
            "filesize": None,
            "filesize_text": None,
            "note": None,
        })

    return result


def _clean_url_candidate(raw):
    u = (raw or "").strip()
    u = _TRAIL_PUNCT_RE.sub("", u)
    # Strip common trailing junk from share apps
    while u and u[-1] in ".,;:!?)]}>\"'":
        u = u[:-1]
    return u


def _host_priority(url):
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return 999
    for i, hint in enumerate(_PREFERRED_HOST_HINTS):
        if host == hint or host.endswith("." + hint) or hint in host:
            return i
    return 500


def extract_url_from_text(text):
    """Pull the best video URL out of Douyin/TikTok/etc share paste text."""
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        # Whole string is (or starts as) a URL — take first token/line
        first = re.split(r"[\s]+", text, maxsplit=1)[0]
        return _clean_url_candidate(first)

    matches = _URL_RE.findall(text)
    if not matches:
        return None
    cleaned = [_clean_url_candidate(m) for m in matches]
    cleaned = [u for u in cleaned if u.startswith("http://") or u.startswith("https://")]
    if not cleaned:
        return None
    cleaned.sort(key=_host_priority)
    return cleaned[0]


def validate_url(url):
    """Normalize paste text / share token into a single http(s) URL."""
    text = (url or "").strip()
    if not text:
        raise YtdlpError("请输入视频链接或分享口令")

    extracted = extract_url_from_text(text)
    if not extracted:
        raise YtdlpError(
            "未在分享内容中找到视频链接，请复制完整分享口令（需包含 https://v.douyin.com/... ）"
        )
    if len(extracted) > 2048:
        raise YtdlpError("链接过长")
    return extracted


def _friendly_extract_error(url: str, exc: BaseException) -> str:
    msg = str(exc)
    low = msg.lower()
    if is_bilibili_url(url) or "bilibili" in low:
        if "412" in msg or "precondition" in low or "http error 412" in low:
            return (
                "B站当前对云服务器访问限制较严（风控 412），网页版暂不稳定。"
                "请优先试试抖音分享口令或 YouTube 链接；B站建议用电脑浏览器本地工具下载。"
            )
        return (
            "暂时无法解析该 B站视频（可能需登录或触发平台风控）。"
            "请改用抖音 / YouTube 等链接，或稍后再试。"
        )
    return "无法解析该视频。链接可能无效、需登录，或平台暂不支持。"


def extract_info(url):
    if is_demo_summary_url(url):
        return demo_video_info()

    if is_douyin_url(url):
        try:
            info = fetch_douyin_info(url)
            info.pop("_douyin_play_urls", None)
            info.pop("_douyin_play_map", None)
            return info
        except DouyinError as exc:
            raise YtdlpError(exc.message, status_code=exc.status_code) from exc

    if is_bilibili_url(url):
        try:
            info = fetch_bilibili_info(url)
            info.pop("_bilibili_play", None)
            return info
        except BilibiliError as exc:
            raise YtdlpError(exc.message, status_code=exc.status_code) from exc

    if is_xiaohongshu_url(url):
        try:
            info = fetch_xiaohongshu_info(url)
            info.pop("_xhs_play_urls", None)
            info.pop("_xhs_play_map", None)
            return info
        except XiaohongshuError as exc:
            raise YtdlpError(exc.message, status_code=exc.status_code) from exc

    opts = _base_opts()
    opts["skip_download"] = True
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except (DownloadError, ExtractorError) as exc:
        logger.warning("extract_info failed: %s", exc)
        raise YtdlpError(_friendly_extract_error(url, exc), status_code=422)
    except Exception as exc:
        logger.exception("unexpected extract error")
        raise YtdlpError("解析失败：{}".format(exc), status_code=500)

    if not info:
        raise YtdlpError("未能获取视频信息", status_code=422)

    if info.get("_type") == "playlist" and info.get("entries"):
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise YtdlpError("播放列表为空", status_code=422)
        info = entries[0]

    return {
        "id": info.get("id"),
        "title": info.get("title") or "未命名视频",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "uploader": info.get("uploader"),
        "webpage_url": info.get("webpage_url") or url,
        "formats": _pick_formats(info),
    }


def download_video(url, format_id):
    if is_douyin_url(url):
        try:
            return download_douyin(url, format_id=format_id)
        except DouyinError as exc:
            raise YtdlpError(exc.message, status_code=exc.status_code) from exc

    if is_bilibili_url(url):
        try:
            return download_bilibili(url, format_id)
        except BilibiliError as exc:
            raise YtdlpError(exc.message, status_code=exc.status_code) from exc

    if is_xiaohongshu_url(url):
        try:
            return download_xiaohongshu(url, format_id=format_id)
        except XiaohongshuError as exc:
            raise YtdlpError(exc.message, status_code=exc.status_code) from exc

    job_dir = TEMP_DIR / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(job_dir / "%(title).80B [%(id)s].%(ext)s")

    opts = _base_opts()
    opts.update({
        "format": format_id or "best",
        "outtmpl": outtmpl,
        "restrictfilenames": True,
        "max_filesize": MAX_DOWNLOAD_BYTES,
    })
    if ffmpeg_available():
        opts["merge_output_format"] = "mp4"

    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except (DownloadError, ExtractorError) as exc:
        remove_dir(job_dir)
        msg = str(exc)
        if "ffmpeg" in msg.lower():
            raise YtdlpError(
                "该清晰度需要 ffmpeg 合并音视频，请安装 ffmpeg 后重试，或选择带音轨的格式。",
                status_code=400,
            )
        raise YtdlpError("下载失败。请换一个清晰度或稍后再试。", status_code=422)
    except Exception as exc:
        remove_dir(job_dir)
        logger.exception("download error")
        raise YtdlpError("下载异常：{}".format(exc), status_code=500)

    files = [
        p for p in job_dir.iterdir()
        if p.is_file() and p.suffix.lower() not in {".json", ".part", ".ytdl", ".temp"}
    ]
    if not files:
        remove_dir(job_dir)
        raise YtdlpError("下载完成但未找到文件", status_code=500)

    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    media = files[0]
    if media.stat().st_size > MAX_DOWNLOAD_BYTES:
        remove_dir(job_dir)
        raise YtdlpError("文件超过体积上限（500MB）", status_code=413)

    return media


def check_ffmpeg_cli():
    path = get_ffmpeg_binary()
    if not path:
        return None
    try:
        r = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first = (r.stdout or "").splitlines()[0] if r.stdout else path
        return first
    except Exception:
        return path
