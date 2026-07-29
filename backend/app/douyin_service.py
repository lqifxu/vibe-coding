"""Douyin share-page resolver — bypasses broken yt-dlp Douyin cookie flow."""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import MAX_DOWNLOAD_BYTES, TEMP_DIR
from .cleanup import remove_dir

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)

_VIDEO_ID_RE = re.compile(
    r"(?:douyin\.com|iesdouyin\.com)/(?:share/)?video/(?P<id>\d+)",
    re.I,
)
_SHORT_HOSTS = ("v.douyin.com", "www.iesdouyin.com")


class DouyinError(Exception):
    def __init__(self, message, status_code=422):
        super(DouyinError, self).__init__(message)
        self.message = message
        self.status_code = status_code


def is_douyin_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(
        host == h or host.endswith("." + h)
        for h in (
            "douyin.com",
            "iesdouyin.com",
            "v.douyin.com",
            "amemv.com",
        )
    )


def _request(url: str, method: str = "GET", timeout: int = 25) -> Tuple[str, bytes, str]:
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": _UA,
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final = resp.geturl()
            data = resp.read() if method != "HEAD" else b""
            ctype = resp.headers.get("Content-Type") or ""
            return final, data, ctype
    except urllib.error.HTTPError as exc:
        # Some endpoints return body on error
        body = exc.read() if hasattr(exc, "read") else b""
        raise DouyinError("请求抖音失败：HTTP {}".format(exc.code)) from exc
    except Exception as exc:
        raise DouyinError("请求抖音失败：{}".format(exc)) from exc


def _unescape(s: str) -> str:
    return s.replace("\\u002F", "/").replace("\\/", "/")


def _extract_id_from_query(url: str):
    """Pick aweme id from modal_id / aweme_id / item_ids / video_id query params."""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    except Exception:
        return None
    for key in ("modal_id", "aweme_id", "item_ids", "video_id"):
        vals = qs.get(key) or []
        for raw in vals:
            # item_ids may be comma-separated
            for part in str(raw).split(","):
                part = part.strip()
                if part.isdigit() and len(part) >= 6:
                    return part
    return None


def _is_douyin_homepage(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "/").rstrip("/") or "/"
    except Exception:
        return False
    if "douyin.com" not in host:
        return False
    # Has explicit video id in path or query — not a bare homepage
    if _VIDEO_ID_RE.search(url) or _extract_id_from_query(url):
        return False
    return path in ("/", "/recommend", "/jingxuan", "/follow", "/friend")


def resolve_video_id(url: str) -> str:
    m = _VIDEO_ID_RE.search(url)
    if m:
        return m.group("id")

    qid = _extract_id_from_query(url)
    if qid:
        return qid

    if _is_douyin_homepage(url):
        raise DouyinError(
            "这是抖音网页推荐页地址（不含视频 ID），不能用来下载。"
            "请复制带 modal_id= 的地址栏链接，或使用「分享 → 复制链接/口令」。"
        )

    # Follow short-link redirects (v.douyin.com/xxx)
    try:
        final, data, _ = _request(url, method="GET", timeout=20)
    except DouyinError:
        raise
    m = _VIDEO_ID_RE.search(final)
    if m:
        return m.group("id")
    qid = _extract_id_from_query(final)
    if qid:
        return qid
    # Sometimes redirect landing HTML still contains video id
    text = data.decode("utf-8", "replace") if data else ""
    m = _VIDEO_ID_RE.search(text) or re.search(r'"aweme_id"\s*:\s*"?(\d+)"?', text)
    if m:
        return m.group(1) if m.lastindex else m.group("id")

    if _is_douyin_homepage(final):
        raise DouyinError(
            "链接跳转到了抖音首页，不是具体视频。"
            "请使用「分享 → 复制链接」或带 modal_id= /video/数字ID 的链接。"
        )
    raise DouyinError(
        "无法从该抖音链接解析视频 ID。"
        "请粘贴完整分享口令、带 modal_id= 的网页链接，"
        "或 https://www.douyin.com/video/数字ID 。无需登录、无需 Cookie。"
    )


def _parse_share_html(html: str, video_id: str) -> Dict[str, Any]:
    html_u = _unescape(html)

    title = None
    for pat in (
        r'"desc"\s*:\s*"((?:\\.|[^"\\])*)"',
        r'"share_title"\s*:\s*"((?:\\.|[^"\\])*)"',
        r"<title>([^<]+)</title>",
    ):
        m = re.search(pat, html)
        if m:
            title = m.group(1)
            try:
                title = json.loads('"{}"'.format(title.replace('"', '\\"'))) if "\\u" in title or "\\" in title else title
            except Exception:
                title = _unescape(title)
            title = re.sub(r"\s*[-|].*抖音.*$", "", title).strip() or title
            break

    author = None
    m = re.search(r'"nickname"\s*:\s*"((?:\\.|[^"\\])*)"', html)
    if m:
        try:
            author = json.loads('"{}"'.format(m.group(1).replace('"', '\\"')))
        except Exception:
            author = _unescape(m.group(1))

    cover = None
    m = re.search(r'"cover"\s*:\s*\{[^}]*?"url_list"\s*:\s*\[\s*"([^"]+)"', html, re.S)
    if m:
        cover = _unescape(m.group(1))

    duration_ms = None
    m = re.search(r'"duration"\s*:\s*(\d+)', html)
    if m:
        # share page duration may be seconds or ms
        val = int(m.group(1))
        duration_ms = val if val > 1000 else val * 1000

    # play_addr uri + url_list
    uri = None
    m = re.search(r'"play_addr"\s*:\s*\{.*?\"uri\"\s*:\s*\"([^\"]+)\"', html, re.S)
    if m:
        uri = m.group(1)

    play_urls: List[str] = []
    m = re.search(r'"play_addr"\s*:\s*\{.*?\"url_list\"\s*:\s*\[(.*?)\]', html, re.S)
    if m:
        play_urls = [_unescape(u) for u in re.findall(r'"(https:[^"]+)"', m.group(1))]

    if uri:
        # Prefer no-watermark play endpoint; fall back to watermarked
        play_urls = [
            "https://www.iesdouyin.com/aweme/v1/play/?video_id={}&ratio=720p&line=0".format(uri),
            "https://aweme.snssdk.com/aweme/v1/play/?video_id={}&ratio=720p&line=0".format(uri),
            "https://www.iesdouyin.com/aweme/v1/playwm/?video_id={}&ratio=720p&line=0".format(uri),
        ] + play_urls

    # dedupe keep order
    seen = set()
    uniq = []
    for u in play_urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    play_urls = uniq

    if not play_urls:
        raise DouyinError("已打开分享页，但未找到可下载的视频地址（可能已失效或需登录）")

    return {
        "id": video_id,
        "title": title or "抖音视频 {}".format(video_id),
        "uploader": author,
        "thumbnail": cover,
        "duration": int(duration_ms / 1000) if duration_ms else None,
        "play_urls": play_urls,
        "webpage_url": "https://www.douyin.com/video/{}".format(video_id),
    }


def fetch_douyin_info(url: str) -> Dict[str, Any]:
    video_id = resolve_video_id(url)
    share_url = "https://www.iesdouyin.com/share/video/{}".format(video_id)
    _, data, _ = _request(share_url)
    html = data.decode("utf-8", "replace")
    meta = _parse_share_html(html, video_id)

    formats = [
        {
            "format_id": "douyin-play",
            "label": "720p",
            "ext": "mp4",
            "height": 720,
            "has_audio": True,
            "filesize": None,
            "filesize_text": None,
            "note": "抖音直链",
        }
    ]
    return {
        "id": meta["id"],
        "title": meta["title"],
        "thumbnail": meta["thumbnail"],
        "duration": meta["duration"],
        "extractor": "Douyin",
        "uploader": meta["uploader"],
        "webpage_url": meta["webpage_url"],
        "formats": formats,
        "_douyin_play_urls": meta["play_urls"],
    }


def download_douyin(url: str, dest_dir: Optional[Path] = None) -> Path:
    info = fetch_douyin_info(url)
    play_urls = info.get("_douyin_play_urls") or []
    job_dir = dest_dir or (TEMP_DIR / str(uuid.uuid4()))
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", info["title"])[:60] or info["id"]
    out_path = job_dir / "{} [{}].mp4".format(safe_title, info["id"])

    last_err = None
    for play in play_urls:
        try:
            req = urllib.request.Request(
                play,
                headers={
                    "User-Agent": _UA,
                    "Referer": "https://www.iesdouyin.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                # Follow redirects already handled; write stream
                total = 0
                with open(out_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise DouyinError("文件超过体积上限（500MB）", status_code=413)
                        f.write(chunk)
                if total < 1000:
                    raise DouyinError("下载内容过小，可能不是视频")
                if "video" not in ctype and total < 50_000:
                    # still accept if looks like mp4 (ftyp)
                    pass
                logger.info("douyin downloaded %s bytes from %s", total, play[:80])
                return out_path
        except DouyinError:
            raise
        except Exception as exc:
            last_err = exc
            logger.warning("douyin play url failed: %s (%s)", play[:80], exc)
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            continue

    remove_dir(job_dir)
    raise DouyinError("抖音视频下载失败：{}".format(last_err or "无可用直链"))
