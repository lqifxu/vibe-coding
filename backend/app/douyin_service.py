"""Douyin share-page resolver — bypasses broken yt-dlp Douyin cookie flow."""
from __future__ import annotations

import json
import logging
import re
import socket
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
_FEED_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
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


def _request(
    url: str,
    method: str = "GET",
    timeout: int = 25,
    user_agent: Optional[str] = None,
) -> Tuple[str, bytes, str]:
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": user_agent or _UA,
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


def _format_size(n: Optional[int]) -> Optional[str]:
    if not n or n <= 0:
        return None
    units = ["B", "KB", "MB", "GB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return "{} {}".format(int(size), unit)
            return "{:.1f} {}".format(size, unit)
        size /= 1024
    return None


def _url_list(addr: Any, *, prefer_no_watermark: bool = True) -> List[str]:
    if isinstance(addr, str) and addr.startswith("http"):
        raw_list = [addr]
    elif isinstance(addr, dict):
        raw_list = list(addr.get("url_list") or [])
    else:
        return []
    out: List[str] = []
    for raw in raw_list:
        if not isinstance(raw, str) or not raw.startswith("http"):
            continue
        url = raw.replace("/playwm/", "/play/") if prefer_no_watermark else raw
        if url not in out:
            out.append(url)
        # Keep watermarked variant too — on cloud IPs it often still has an audio track.
        if prefer_no_watermark and "/play/" in raw and "/playwm/" not in raw:
            wm = raw.replace("/play/", "/playwm/")
            if wm not in out:
                out.append(wm)
    return out


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _host_resolves(host: str) -> bool:
    """Prefer IPv4 — many CN cloud VPSes resolve AAAA but cannot route IPv6."""
    try:
        socket.getaddrinfo(host, 443, socket.AF_INET)
        return True
    except OSError:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            return False


def _ipv4_fetch_url(url: str) -> Tuple[str, Dict[str, str]]:
    """Rewrite URL host to IPv4 literal and return extra Host header."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    extra: Dict[str, str] = {}
    if not host:
        return url, extra
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
        ip = infos[0][4][0]
    except OSError:
        return url, extra
    netloc = ip
    if parsed.port:
        netloc = "{}:{}".format(ip, parsed.port)
    extra["Host"] = host
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc)), extra


def _expand_music_cdn(urls: List[str]) -> List[str]:
    """Same object on several douyinstatic hosts; skip hosts that do not resolve."""
    # Only well-known sf*-cdn-tos hosts. Fake v95-music etc. break cloud DNS.
    hosts = (
        "sf3-cdn-tos.douyinstatic.com",
        "sf6-cdn-tos.douyinstatic.com",
        "sf1-cdn-tos.douyinstatic.com",
    )
    live_hosts = [h for h in hosts if _host_resolves(h)]
    out: List[str] = []
    for raw in urls:
        try:
            parsed = urllib.parse.urlparse(raw)
            host = (parsed.hostname or "").lower()
            path = parsed.path or ""
        except Exception:
            continue
        if host and not _host_resolves(host):
            logger.warning("skip unresolvable douyin host: %s", host)
            continue
        if raw not in out:
            out.append(raw)
        if "/obj/ies-music/" not in path and "/ies-music/" not in path:
            continue
        for host in live_hosts:
            alt = urllib.parse.urlunparse(
                ("https", host, path, "", parsed.query or "", "")
            )
            if alt not in out:
                out.append(alt)
    return out


def _music_urls_from_aweme(item: Dict[str, Any]) -> List[str]:
    """Douyin bit_rate play_addr is often video-only; music.play_url has the audio."""
    music = item.get("music") if isinstance(item.get("music"), dict) else {}
    urls: List[str] = []
    for key in ("play_url", "play_url_lowbr", "play_url_h264"):
        for u in _url_list(music.get(key)):
            if u not in urls:
                urls.append(u)
    # Some payloads only expose music id / uri — synthesize CDN paths.
    mid = str(music.get("id") or music.get("id_str") or "").strip()
    for key in ("play_url", "play_url_lowbr"):
        addr = music.get(key)
        if isinstance(addr, dict):
            uri = str(addr.get("uri") or "").strip()
            if uri and not uri.startswith("http") and uri not in mid:
                mid = mid or uri
    if mid and mid.isdigit():
        synth = "https://sf3-cdn-tos.douyinstatic.com/obj/ies-music/{}.mp3".format(mid)
        if synth not in urls:
            urls.append(synth)
    return _expand_music_cdn(urls)


def _muxed_play_urls_from_uri(uri: Optional[str]) -> List[str]:
    """Watermarked playwm often keeps audio on cloud IPs; try it before no-WM play."""
    if not uri:
        return []
    urls = [
        "https://aweme.snssdk.com/aweme/v1/playwm/?video_id={}&ratio=720p&line=0".format(uri),
        "https://aweme.snssdk.com/aweme/v1/play/?video_id={}&ratio=720p&line=0".format(uri),
        "https://www.iesdouyin.com/aweme/v1/playwm/?video_id={}&ratio=720p&line=0".format(uri),
        "https://www.iesdouyin.com/aweme/v1/play/?video_id={}&ratio=720p&line=0".format(uri),
    ]
    return [u for u in urls if _host_resolves(urllib.parse.urlparse(u).hostname or "")]


def _video_uri(video: Dict[str, Any]) -> Optional[str]:
    for key in ("play_addr_h264", "play_addr", "download_addr"):
        addr = video.get(key)
        if isinstance(addr, dict):
            uri = addr.get("uri") or addr.get("url_key")
            if uri:
                return str(uri)
    for br in video.get("bit_rate") or []:
        if not isinstance(br, dict):
            continue
        addr = br.get("play_addr") or {}
        if isinstance(addr, dict):
            uri = addr.get("uri") or addr.get("url_key")
            if uri:
                return str(uri)
    return None


def _fetch_aweme_item(video_id: str) -> Optional[Dict[str, Any]]:
    """Public feed endpoint still returns the requested aweme without a signature."""
    api = (
        "https://aweme.snssdk.com/aweme/v1/feed/"
        "?aweme_id={}&version_code=280000&app_name=aweme&device_platform=android"
    ).format(video_id)
    try:
        _, data, _ = _request(api, timeout=20, user_agent=_FEED_UA)
    except DouyinError as exc:
        logger.warning("douyin feed api failed: %s", exc)
        return None
    if not data:
        return None
    try:
        payload = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        logger.warning("douyin feed api returned non-json")
        return None
    if not isinstance(payload, dict):
        return None
    for item in payload.get("aweme_list") or []:
        if isinstance(item, dict) and str(item.get("aweme_id") or "") == str(video_id):
            return item
    return None


def _streams_from_video(video: Dict[str, Any], allow_h265: bool) -> List[Dict[str, Any]]:
    streams: List[Dict[str, Any]] = []
    for br in video.get("bit_rate") or []:
        if not isinstance(br, dict):
            continue
        if br.get("is_h265") and not allow_h265:
            continue
        addr = br.get("play_addr") or {}
        urls = _url_list(addr)
        if not urls:
            continue
        width = _as_int(addr.get("width"))
        height = _as_int(addr.get("height"))
        short = min(width, height) if width and height else (height or width)
        streams.append(
            {
                "short": short,
                "height": height or None,
                "bitrate": _as_int(br.get("bit_rate")),
                "size": _as_int(addr.get("data_size")) or None,
                "urls": urls,
            }
        )
    return streams


def _meta_from_aweme(item: Dict[str, Any], video_id: str) -> Dict[str, Any]:
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    streams = _streams_from_video(video, allow_h265=False)
    if not streams:
        streams = _streams_from_video(video, allow_h265=True)
    if not streams:
        for key in ("play_addr_h264", "play_addr", "download_addr"):
            urls = _url_list(video.get(key))
            if urls:
                addr = video.get(key) or {}
                height = _as_int(addr.get("height")) or _as_int(video.get("height"))
                width = _as_int(addr.get("width")) or _as_int(video.get("width"))
                short = min(width, height) if width and height else (height or width)
                streams.append(
                    {
                        "short": short,
                        "height": height or None,
                        "bitrate": 0,
                        "size": _as_int(addr.get("data_size")) or None,
                        "urls": urls,
                    }
                )
                break
    if not streams:
        images = item.get("images") or item.get("image_infos")
        if images:
            raise DouyinError("这是图文作品，当前只支持视频下载")
        raise DouyinError("已找到该作品，但没有可下载的视频地址（可能已失效或为直播）")

    best: Dict[int, Dict[str, Any]] = {}
    for stream in streams:
        key = stream["short"] or stream["bitrate"] or len(best)
        prev = best.get(key)
        if prev is None or stream["bitrate"] > prev["bitrate"]:
            best[key] = stream
    ordered = sorted(best.values(), key=lambda s: (s["short"], s["bitrate"]), reverse=True)

    formats: List[Dict[str, Any]] = []
    play_map: Dict[str, List[str]] = {}
    for stream in ordered:
        short = stream["short"] or 0
        fid = "douyin-{}".format(short) if short else "douyin-play"
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
                "note": "抖音直链",
            }
        )
        play_map[fid] = stream["urls"]

    muxed = _muxed_play_urls_from_uri(_video_uri(video))
    audio_urls = _music_urls_from_aweme(item)
    if formats:
        primary = list(play_map[formats[0]["format_id"]])
        # Prefer muxed (with audio) for default download / ASR fallback.
        play_map["douyin-play"] = muxed + [u for u in primary if u not in muxed] if muxed else primary
    elif muxed:
        play_map["douyin-play"] = muxed

    cover = None
    for key in ("origin_cover", "cover", "dynamic_cover"):
        urls = _url_list(video.get(key))
        if urls:
            cover = urls[0]
            break
    duration_ms = _as_int(video.get("duration")) or _as_int(item.get("duration"))
    author = None
    author_obj = item.get("author")
    if isinstance(author_obj, dict):
        author = author_obj.get("nickname") or None
    title = (item.get("desc") or "").strip() or "抖音视频 {}".format(video_id)
    return {
        "id": video_id,
        "title": title,
        "uploader": author,
        "thumbnail": cover,
        "duration": int(duration_ms / 1000) if duration_ms > 1000 else (duration_ms or None),
        "formats": formats,
        "play_map": play_map,
        "audio_urls": audio_urls,
        "webpage_url": "https://www.douyin.com/video/{}".format(video_id),
    }


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
        play_urls = _muxed_play_urls_from_uri(uri) + play_urls

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

    audio_urls: List[str] = []
    m = re.search(r'"play_url"\s*:\s*\{.*?\"url_list\"\s*:\s*\[(.*?)\]', html, re.S)
    if m:
        for u in re.findall(r'"(https:[^"]+)"', m.group(1)):
            u = _unescape(u)
            if u not in audio_urls:
                audio_urls.append(u)

    return {
        "id": video_id,
        "title": title or "抖音视频 {}".format(video_id),
        "uploader": author,
        "thumbnail": cover,
        "duration": int(duration_ms / 1000) if duration_ms else None,
        "formats": [
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
        ],
        "play_map": {"douyin-play": play_urls},
        "audio_urls": audio_urls,
        "webpage_url": "https://www.douyin.com/video/{}".format(video_id),
    }


def _public_info(meta: Dict[str, Any]) -> Dict[str, Any]:
    play_map = meta.get("play_map") or {}
    flat: List[str] = []
    for urls in play_map.values():
        for url in urls:
            if url not in flat:
                flat.append(url)
    audio_urls = list(meta.get("audio_urls") or [])
    return {
        "id": meta["id"],
        "title": meta["title"],
        "thumbnail": meta.get("thumbnail"),
        "duration": meta.get("duration"),
        "extractor": "Douyin",
        "uploader": meta.get("uploader"),
        "webpage_url": meta.get("webpage_url"),
        "formats": meta.get("formats") or [],
        "_douyin_play_map": play_map,
        "_douyin_play_urls": flat,
        "_douyin_audio_urls": audio_urls,
    }


def fetch_douyin_info(url: str) -> Dict[str, Any]:
    video_id = resolve_video_id(url)
    item = _fetch_aweme_item(video_id)
    if item:
        return _public_info(_meta_from_aweme(item, video_id))

    share_url = "https://www.iesdouyin.com/share/video/{}".format(video_id)
    _, data, _ = _request(share_url)
    html = data.decode("utf-8", "replace")
    return _public_info(_parse_share_html(html, video_id))


def _download_urls_to_file(
    urls: List[str],
    out_path: Path,
    min_bytes: int = 1000,
) -> Path:
    """Prefer curl_cffi (Chrome TLS) — cloud urllib often gets empty/blocked CDN bodies."""
    last_err = None
    headers = {
        "User-Agent": _FEED_UA,
        "Referer": "https://www.douyin.com/",
        "Origin": "https://www.douyin.com",
        "Accept": "*/*",
    }

    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        cffi_requests = None

    for play in urls:
        try:
            total = 0
            fetch_url, host_hdr = _ipv4_fetch_url(play)
            req_headers = dict(headers)
            req_headers.update(host_hdr)
            if cffi_requests is not None:
                # verify=False when using IPv4 literal + Host (SNI/cert name mismatch).
                resp = cffi_requests.get(
                    fetch_url,
                    impersonate="chrome131",
                    headers=req_headers,
                    timeout=60,
                    allow_redirects=True,
                    verify=fetch_url == play,
                )
                if resp.status_code >= 400:
                    raise DouyinError("下载失败：HTTP {}".format(resp.status_code))
                data = resp.content or b""
                total = len(data)
                if total > MAX_DOWNLOAD_BYTES:
                    raise DouyinError("文件超过体积上限（500MB）", status_code=413)
                if total < min_bytes:
                    raise DouyinError("下载内容过小，可能不是媒体文件")
                # HTML login / error pages are not media
                head = data[:200].lstrip().lower()
                if head.startswith(b"<!DOCTYPE") or head.startswith(b"<html"):
                    raise DouyinError("CDN 返回了网页而不是媒体")
                out_path.write_bytes(data)
            else:
                req = urllib.request.Request(fetch_url, headers=req_headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    with open(out_path, "wb") as f:
                        while True:
                            chunk = resp.read(1024 * 256)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > MAX_DOWNLOAD_BYTES:
                                raise DouyinError("文件超过体积上限（500MB）", status_code=413)
                            f.write(chunk)
                if total < min_bytes:
                    raise DouyinError("下载内容过小，可能不是媒体文件")
            logger.info("douyin downloaded %s bytes from %s", total, play[:80])
            return out_path
        except DouyinError as exc:
            last_err = exc
            logger.warning("douyin media url failed: %s (%s)", play[:80], exc)
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            continue
        except Exception as exc:
            last_err = exc
            logger.warning("douyin media url failed: %s (%s)", play[:80], exc)
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            continue
    raise DouyinError("抖音媒体下载失败：{}".format(last_err or "无可用直链"))


def download_douyin(
    url: str,
    dest_dir: Optional[Path] = None,
    format_id: Optional[str] = None,
) -> Path:
    info = fetch_douyin_info(url)
    play_map = info.get("_douyin_play_map") or {}
    fid = (format_id or "").strip()
    play_urls = list(play_map.get(fid) or [])
    if not play_urls:
        play_urls = list(play_map.get("douyin-play") or [])
    if not play_urls:
        play_urls = list(info.get("_douyin_play_urls") or [])
    job_dir = dest_dir or (TEMP_DIR / str(uuid.uuid4()))
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", info["title"])[:60] or info["id"]
    out_path = job_dir / "{} [{}].mp4".format(safe_title, info["id"])

    try:
        return _download_urls_to_file(play_urls, out_path)
    except DouyinError:
        remove_dir(job_dir)
        raise


def download_douyin_for_asr(url: str, dest_dir: Optional[Path] = None) -> Path:
    """Prefer music audio / muxed play for speech-to-text (bit_rate CDN is often silent)."""
    from .asr_service import media_has_audio

    info = fetch_douyin_info(url)
    job_dir = dest_dir or (TEMP_DIR / str(uuid.uuid4()))
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", info["title"])[:60] or info["id"]

    candidates: List[Tuple[str, List[str]]] = []
    # 1) Official music CDN (resolvable hosts only).
    audio_urls = _expand_music_cdn(list(info.get("_douyin_audio_urls") or []))
    if audio_urls:
        ext = "mp3" if any(".mp3" in u.lower() for u in audio_urls) else "m4a"
        candidates.append((ext, audio_urls))
    # 2) Watermarked / muxed play (snssdk) — often the only with-audio option on VPS.
    play_map = info.get("_douyin_play_map") or {}
    play_urls = list(play_map.get("douyin-play") or []) or list(
        info.get("_douyin_play_urls") or []
    )
    # Prefer playwm URLs first for ASR.
    play_urls = sorted(
        play_urls,
        key=lambda u: (0 if "playwm" in u else 1, 0 if "snssdk.com" in u else 1),
    )
    if play_urls:
        candidates.append(("mp4", play_urls))

    last_err: Optional[BaseException] = None
    for ext, urls in candidates:
        # Try URLs one-by-one so a silent CDN file does not block a later good URL.
        for play in urls:
            use_ext = "mp3" if ".mp3" in play.lower() else ext
            out_path = job_dir / "{} [{}].{}".format(safe_title, info["id"], use_ext)
            try:
                path = _download_urls_to_file([play], out_path, min_bytes=500)
                if media_has_audio(path):
                    return path
                logger.warning("douyin ASR candidate has no audio: %s", play[:80])
                try:
                    path.unlink()
                except OSError:
                    pass
            except DouyinError as exc:
                last_err = exc
                logger.warning("douyin ASR candidate failed: %s (%s)", play[:80], exc)

    remove_dir(job_dir)
    raise DouyinError(
        "抖音没有下到带音轨的文件，无法语音转写：{}".format(last_err or "直链均为无声")
    )
