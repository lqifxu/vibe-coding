"""Local demo video fixture for AI summary E2E testing (no network)."""
from __future__ import annotations

from typing import Any, Dict, List

DEMO_SUMMARY_URL = "https://jisuxia.local/demo/ai-summary"

# Thematic stand-in for BV133411C7u5 (Python learning route) when CC requires login.
_DEMO_CUES: List[Dict[str, Any]] = [
    {"start_sec": 0, "start": "00:00", "text": "大家好，这份是2025年最新保姆级 Python 学习路线，适合零基础到求职。"},
    {"start_sec": 25, "start": "00:25", "text": "第一阶段先打牢语法：变量、条件、循环、函数和基础数据结构。"},
    {"start_sec": 70, "start": "01:10", "text": "第二阶段做项目驱动：爬虫入门、数据分析 pandas、以及一个小 Web 服务。"},
    {"start_sec": 130, "start": "02:10", "text": "第三阶段补工程化：虚拟环境、Git、代码规范、调试和阅读官方文档的习惯。"},
    {"start_sec": 190, "start": "03:10", "text": "进阶方向可以按兴趣选：自动化运维、数据科学，或后端开发 Django / FastAPI。"},
    {"start_sec": 250, "start": "04:10", "text": "学习建议是每天固定学习时长，写笔记复盘，并把每个知识点做成可运行小例子。"},
    {"start_sec": 300, "start": "05:00", "text": "最后，路线不是越长越好，完成一个可展示项目比盲目刷课更重要。"},
]


def is_demo_summary_url(url: str) -> bool:
    u = (url or "").strip().rstrip("/")
    return u == DEMO_SUMMARY_URL or u.startswith(DEMO_SUMMARY_URL + "?")


def demo_video_info() -> Dict[str, Any]:
    return {
        "id": "jisuxia-demo-ai-summary",
        "title": "2025年最新保姆级Python学习路线，零基础到精通一条龙（演示字幕）",
        "thumbnail": None,
        "duration": 320,
        "extractor": "jisuxia_demo",
        "uploader": "极速下演示",
        "webpage_url": DEMO_SUMMARY_URL,
        "formats": [
            {
                "format_id": "demo-720",
                "label": "720P",
                "ext": "mp4",
                "height": 720,
                "has_audio": True,
                "filesize": 12_000_000,
                "filesize_text": "11.4 MB",
                "note": "演示用，不可真实下载",
            }
        ],
    }


def demo_subtitles(max_chars: int) -> Dict[str, Any]:
    cues = list(_DEMO_CUES)
    lines = ["[{}] {}".format(c["start"], c["text"]) for c in cues]
    transcript = "\n".join(lines)
    if len(transcript) > max_chars:
        transcript = transcript[: max_chars - 1] + "…"
    return {
        "title": "2025年最新保姆级Python学习路线，零基础到精通一条龙（演示字幕）",
        "language": "zh",
        "source": "manual",
        "cues": cues,
        "transcript": transcript,
        "webpage_url": DEMO_SUMMARY_URL,
    }
