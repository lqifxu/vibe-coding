"""Bilibili resolver via public API — avoids www.bilibili.com 412 on cloud IPs."""
from __future__ import annotations

import json
import logging
import os
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_BV_RE = re.compile(r"(BV[\w]+)", re.I)
_AV_RE = re.compile(r"(?:av|AV)(\d+)")
_EP_RE = re.compile(r"/bangumi/play/ep(\d+)", re.I)

# qn -> (label, height) for progressive MP4 (fnval=1 / html5)
_QN_META = {
    16: ("360p", 360),
    32: ("480p", 480),
    64: ("720p", 720),
    80: ("1080p", 1080),
    112: ("1080p+", 1080),
    116: ("1080p60", 1080),
    120: ("4K", 2160),
}


class BilibiliError(Exception):
    def __init__(self, message, status_code=422):
        super(BilibiliError, self).__init__(message)
        self.message = message
        self.status_code = status_code


def is_bilibili_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return (
        "bilibili.com" in host
        or host == "b23.tv"
        or host.endswith(".b23.tv")
        or host == "bili2233.cn"
        or host.endswith(".bili2233.cn")
    )


def _cookie_header() -> str:
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


def _headers() -> Dict[str, str]:
    h = {
        "User-Agent": _UA,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://www.bilibili.com",
    }
    cookie = _cookie_header()
    if cookie:
        h["Cookie"] = cookie
    return h


def _http_json(url: str, timeout: int = 25) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise BilibiliError("请求 B站 API 失败：HTTP {}".format(exc.code)) from exc
    except Exception as exc:
        raise BilibiliError("请求 B站 API 失败：{}".format(exc)) from exc


def _follow_redirect(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl() or url
    except urllib.error.HTTPError as exc:
        # Some short links still expose Location / final URL on error
        loc = exc.headers.get("Location") if exc.headers else None
        if loc:
            return urllib.parse.urljoin(url, loc)
        raise BilibiliError("短链跳转失败：HTTP {}".format(exc.code)) from exc
    except Exception as exc:
        raise BilibiliError("短链跳转失败：{}".format(exc)) from exc


def _page_index(url: str) -> int:
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        vals = qs.get("p") or []
        if vals and str(vals[0]).isdigit():
            return max(1, int(vals[0]))
    except Exception:
        pass
    return 1


def resolve_ids(url: str) -> Tuple[Optional[str], Optional[int], int]:
    """Return (bvid, avid, page_index)."""
    page = _page_index(url)
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host == "b23.tv" or host.endswith(".b23.tv") or "bili2233.cn" in host:
        url = _follow_redirect(url)
        page = _page_index(url) or page

    m = _BV_RE.search(url)
    if m:
        return m.group(1), None, page
    m = _AV_RE.search(url)
    if m:
        return None, int(m.group(1)), page
    raise BilibiliError(
        "无法识别该 B站链接。请粘贴完整视频地址（含 BV 号），"
        "例如 https://www.bilibili.com/video/BVxxxx 。"
    )


def _format_size(n: Optional[int]) -> Optional[str]:
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


def _fetch_view(bvid: Optional[str], avid: Optional[int]) -> Dict[str, Any]:
    if bvid:
        api = "https://api.bilibili.com/x/web-interface/view?bvid={}".format(
            urllib.parse.quote(bvid)
        )
    else:
        api = "https://api.bilibili.com/x/web-interface/view?aid={}".format(avid)
    payload = _http_json(api)
    if payload.get("code") != 0 or not payload.get("data"):
        raise BilibiliError(
            "获取视频信息失败：{}".format(payload.get("message") or payload.get("code"))
        )
    return payload["data"]


def _playurl_mp4(bvid: str, cid: int, qn: int) -> Optional[Dict[str, Any]]:
    """Prefer progressive MP4 (audio+video) to avoid ffmpeg merge."""
    candidates = [
        (
            "https://api.bilibili.com/x/player/wbi/playurl"
            "?bvid={bvid}&cid={cid}&qn={qn}&fnval=1&fourk=1&platform=html5&high_quality=1"
        ),
        (
            "https://api.bilibili.com/x/player/playurl"
            "?bvid={bvid}&cid={cid}&qn={qn}&fnval=1&fourk=1"
        ),
    ]
    for tmpl in candidates:
        url = tmpl.format(bvid=urllib.parse.quote(bvid), cid=cid, qn=qn)
        try:
            payload = _http_json(url)
        except BilibiliError as exc:
            logger.warning("playurl qn=%s failed: %s", qn, exc)
            continue
        if payload.get("code") != 0:
            continue
        data = payload.get("data") or {}
        durl = data.get("durl") or []
        if not durl:
            continue
        item = durl[0]
        play = item.get("url") or (item.get("backup_url") or [None])[0]
        if not play:
            continue
        got_qn = int(data.get("quality") or qn)
        return {
            "qn": got_qn,
            "url": play,
            "size": item.get("size"),
            "backup": list(item.get("backup_url") or []),
        }
    return None


def fetch_bilibili_info(url: str) -> Dict[str, Any]:
    if _EP_RE.search(url):
        raise BilibiliError(
            "暂不支持番剧/影视 EP 链接，请粘贴普通投稿视频（/video/BVxxxx）。"
        )

    bvid, avid, page = resolve_ids(url)
    view = _fetch_view(bvid, avid)
    bvid = view.get("bvid") or bvid
    avid = view.get("aid") or avid
    pages = view.get("pages") or []
    if not pages:
        cid = view.get("cid")
        if not cid:
            raise BilibiliError("该视频没有可播放分 P")
        pages = [{"cid": cid, "page": 1, "part": view.get("title") or ""}]

    idx = min(max(page, 1), len(pages)) - 1
    part = pages[idx]
    cid = int(part["cid"])
    part_title = (part.get("part") or "").strip()

    title = (view.get("title") or "B站视频").strip()
    if len(pages) > 1 and part_title and part_title != title:
        title = "{} - P{} {}".format(title, idx + 1, part_title)

    owner = (view.get("owner") or {}).get("name")
    thumb = view.get("pic")
    duration = part.get("duration") or view.get("duration")

    # Probe common qualities; dedupe by returned qn
    formats: List[Dict[str, Any]] = []
    play_map: Dict[str, Dict[str, Any]] = {}
    seen_qn = set()
    for qn in (120, 116, 112, 80, 64, 32, 16):
        hit = _playurl_mp4(bvid, cid, qn)
        if not hit:
            continue
        got = hit["qn"]
        if got in seen_qn:
            continue
        seen_qn.add(got)
        label, height = _QN_META.get(got, ("{}p".format(got), None))
        fid = "bili-{}".format(got)
        formats.append(
            {
                "format_id": fid,
                "label": label,
                "ext": "mp4",
                "height": height,
                "has_audio": True,
                "filesize": hit.get("size"),
                "filesize_text": _format_size(hit.get("size")),
                "note": "B站直链",
            }
        )
        play_map[fid] = hit

    if not formats:
        raise BilibiliError(
            "已获取视频信息，但暂时拿不到可下载地址（可能触发平台限制）。"
            "请稍后再试，或改用抖音 / YouTube 链接。"
        )

    # Prefer higher quality first
    formats.sort(key=lambda f: f.get("height") or 0, reverse=True)
    best_id = formats[0]["format_id"]
    play_map["best"] = play_map[best_id]
    play_map["bili-play"] = play_map[best_id]

    return {
        "id": bvid or str(avid),
        "title": title,
        "thumbnail": thumb,
        "duration": int(duration) if duration else None,
        "extractor": "Bilibili",
        "uploader": owner,
        "webpage_url": "https://www.bilibili.com/video/{}/".format(bvid)
        if bvid
        else url,
        "formats": formats,
        "_bilibili_play": play_map,
    }


def download_bilibili(url: str, format_id: Optional[str] = None) -> Path:
    info = fetch_bilibili_info(url)
    play_map: Dict[str, Dict[str, Any]] = info.get("_bilibili_play") or {}
    fid = (format_id or "best").strip() or "best"
    if fid not in play_map:
        # Allow bare qn like "80"
        alt = "bili-{}".format(fid) if fid.isdigit() else None
        if alt and alt in play_map:
            fid = alt
        else:
            fid = "best"
    hit = play_map.get(fid) or play_map.get("best")
    if not hit:
        raise BilibiliError("没有可用的下载地址")

    job_dir = TEMP_DIR / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", info["title"])[:60] or info["id"]
    out_path = job_dir / "{} [{}].mp4".format(safe_title, info["id"])

    urls = [hit["url"]] + list(hit.get("backup") or [])
    last_err = None
    for play in urls:
        try:
            req = urllib.request.Request(play, headers=_headers())
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = 0
                with open(out_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise BilibiliError("文件超过体积上限（500MB）", status_code=413)
                        f.write(chunk)
                if total < 1000:
                    raise BilibiliError("下载内容过小，可能不是视频")
                logger.info("bilibili downloaded %s bytes qn=%s", total, hit.get("qn"))
                return out_path
        except BilibiliError:
            raise
        except Exception as exc:
            last_err = exc
            logger.warning("bilibili play url failed: %s (%s)", play[:80], exc)
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            continue

    remove_dir(job_dir)
    raise BilibiliError("B站视频下载失败：{}".format(last_err or "无可用直链"))
