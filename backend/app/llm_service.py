"""OpenAI-compatible Chat Completions via official openai SDK (default DeepSeek)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, Iterator, List, Optional

from openai import APIConnectionError, APIError, AuthenticationError, OpenAI

from .summary_config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from .ytdlp_service import YtdlpError

logger = logging.getLogger(__name__)

_SYSTEM = """你是专业的视频学习助手。根据带时间戳的字幕，用中文输出结构化学习笔记。
只输出一个 JSON 对象，不要 Markdown 代码块，不要其它说明。
风格对齐主流「视频 AI 总结」产品：层次清晰、关键词加粗感（用字段承载，不要输出 Markdown 符号）。

JSON schema:
{
  "overview": "视频概述：一段连贯段落（约80-180字），说明主题、做了什么、结论或价值",
  "outline": [
    {
      "title": "大纲章节标题（短，如：项目介绍与背景；不要把时间戳写进标题）",
      "start": "MM:SS 或 HH:MM:SS，取自字幕附近时间戳",
      "points": [
        {
          "label": "可选小标题，如 操作流程 / 开发工具；没有则空字符串",
          "text": "该条具体内容，1-2句，信息密度高"
        }
      ]
    }
  ],
  "highlights": [
    {
      "title": "要点标题，如 项目价值 / 技术实现",
      "text": "该要点的一句解释"
    }
  ],
  "conclusion": "总结：一段收束性段落（约40-100字），点明对观众的价值或行动建议"
}

要求：
- overview / conclusion / outline / highlights 四个字段都必须有实质内容，禁止空数组或空字符串
- overview / conclusion 必须是段落，不要列表
- outline 按时间升序，通常 3-6 个章节；每章 points 至少 2 条
- highlights 至少 4 条、至多 7 条；title 简短有力，text 解释清楚
- start 必须贴近字幕时间戳；不要编造字幕中不存在的事实
- 兼容旧字段时：若你误输出 summary，则视为 overview；若误输出 chapters，则尽量映射到 outline
"""

_STREAM_SYSTEM = """你是专业的视频学习助手。根据带时间戳的字幕，用中文流式输出学习笔记。
严格按下面四个一级标题顺序输出 Markdown（不要输出其它一级标题，不要代码块）：

## 视频概述
（一段 80-180 字连贯段落）

## 内容大纲
1. **章节标题**
   - **小标题:** 具体内容
   - 具体内容
2. **下一章**
   - …

## 核心知识要点
1. **要点标题:** 一句解释
2. **要点标题:** 一句解释

## 总结
（一段 40-100 字收束段落）

要求：
- 四段都必须有实质内容；不要编造字幕中不存在的事实
- 大纲通常 3-6 章，要点 4-7 条
- 章节标题与要点标题中不要写时间戳（不要出现 00:00 / [01:10] / （03:25）等）
- 不要输出多余说明、前言或结尾客套
"""

_QA_SYSTEM = """你是视频学习助教。请仅根据给定字幕与已有总结回答用户问题。
用简洁中文作答；若字幕中没有依据，明确说明「字幕里没有足够信息」。
可引用时间戳（如 01:20）帮助定位。
"""


def llm_configured() -> bool:
    return bool(LLM_API_KEY)


def _client() -> OpenAI:
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=120.0)


def _parse_start_to_sec(start: str) -> int:
    parts = (start or "0").strip().split(":")
    try:
        nums = [int(float(p)) for p in parts]
    except ValueError:
        return 0
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1:
        return nums[0]
    return 0


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_points(raw: Any) -> List[Dict[str, str]]:
    points: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return points
    for item in raw:
        if isinstance(item, dict):
            label = _as_str(item.get("label") or item.get("title"))
            text = _as_str(item.get("text") or item.get("content") or item.get("summary"))
            if not text and label:
                text = label
                label = ""
            if text:
                points.append({"label": label, "text": text})
        else:
            text = _as_str(item)
            if text:
                m = re.match(r"^\*{0,2}([^*:：]+)\*{0,2}\s*[:：]\s*(.+)$", text)
                if m:
                    points.append({"label": m.group(1).strip(), "text": m.group(2).strip()})
                else:
                    points.append({"label": "", "text": text})
    return points[:8]


def _normalize_highlights(raw: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    for item in raw:
        if isinstance(item, dict):
            title = _as_str(item.get("title") or item.get("label"))
            text = _as_str(item.get("text") or item.get("content") or item.get("summary"))
            if not text and title:
                text = title
                title = ""
            if text:
                out.append({"title": title or "要点", "text": text})
        else:
            text = _as_str(item)
            if not text:
                continue
            m = re.match(r"^\*{0,2}([^*:：]+)\*{0,2}\s*[:：]\s*(.+)$", text)
            if m:
                out.append({"title": m.group(1).strip(), "text": m.group(2).strip()})
            else:
                out.append({"title": "要点", "text": text})
    return out[:8]


def _normalize_outline(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    outline_raw = data.get("outline")
    if not isinstance(outline_raw, list) or not outline_raw:
        outline_raw = data.get("chapters") or []

    outline_out: List[Dict[str, Any]] = []
    if not isinstance(outline_raw, list):
        return outline_out

    for ch in outline_raw:
        if not isinstance(ch, dict):
            continue
        start = _as_str(ch.get("start") or "00:00") or "00:00"
        title = _as_str(ch.get("title")) or "章节"
        # Titles must not carry markdown / timeline (timeline lives in `start`)
        title = re.sub(r"`+", "", title).replace("**", "").replace("__", "").replace("*", "")
        title = re.sub(
            r"\s*[（(\[【]\s*\d{1,2}:\d{2}(?::\d{2})?\s*[）)\]】]\s*",
            " ",
            title,
        )
        title = re.sub(r"\s+", " ", title).strip() or "章节"
        points = _normalize_points(ch.get("points") or ch.get("bullets") or ch.get("items"))
        if not points:
            summary = _as_str(ch.get("summary") or ch.get("text") or ch.get("content"))
            if summary:
                points = [{"label": "", "text": summary}]
        outline_out.append(
            {
                "start": start,
                "start_sec": _parse_start_to_sec(start),
                "title": title,
                "points": points,
            }
        )
    outline_out.sort(key=lambda c: c["start_sec"])
    return outline_out


def _normalize_result(data: Dict[str, Any], title: str) -> Dict[str, Any]:
    overview = _as_str(data.get("overview") or data.get("summary"))
    conclusion = _as_str(data.get("conclusion") or data.get("closing") or data.get("ending"))
    highlights = _normalize_highlights(data.get("highlights") or [])
    outline = _normalize_outline(data)
    outline = [o for o in outline if o.get("points")]

    if not overview and highlights:
        overview = "；".join(
            ("{}：{}".format(h["title"], h["text"]) if h.get("title") else h["text"])
            for h in highlights[:3]
        )
    if not overview and outline:
        overview = "本视频主要围绕「{}」展开，覆盖{}等环节。".format(
            title or "主题内容",
            "、".join(o["title"] for o in outline[:4]),
        )
    if not overview:
        overview = "本视频围绕「{}」展开讲解，建议结合下方大纲与要点系统学习。".format(
            title or "该主题"
        )

    if not outline:
        outline = [
            {
                "start": "00:00",
                "start_sec": 0,
                "title": "内容导读",
                "points": [
                    {"label": "主题", "text": overview[:120]},
                    {"label": "建议", "text": "按时间轴回看关键片段，并记录自己的疑问。"},
                ],
            }
        ]
    else:
        for o in outline:
            if not o.get("points"):
                o["points"] = [{"label": "", "text": o.get("title") or "详见字幕原文"}]

    if not highlights:
        highlights = []
        for o in outline[:5]:
            first = (o.get("points") or [{}])[0]
            highlights.append(
                {
                    "title": o.get("title") or "要点",
                    "text": first.get("text") or overview[:80],
                }
            )
        if len(highlights) < 3:
            highlights.extend(
                [
                    {"title": "学习建议", "text": "边看边记关键词，看完用自己的话复述一遍。"},
                    {"title": "实践导向", "text": "把视频中的方法落到一个小练习或小项目上。"},
                    {"title": "复习路径", "text": "按大纲时间戳回看薄弱环节。"},
                ]
            )
        highlights = highlights[:7]

    if not conclusion:
        conclusion = (
            "综上，「{}」的核心内容已覆盖在概述、大纲与要点中。"
            "建议按大纲回看关键片段，并结合要点动手练习，以巩固理解。"
        ).format(title or "本视频")

    legacy_highlights = [
        ("{}：{}".format(h["title"], h["text"]) if h.get("title") else h["text"])
        for h in highlights
    ]
    legacy_chapters = [
        {
            "start": o["start"],
            "start_sec": o["start_sec"],
            "title": o["title"],
            "summary": "；".join(
                ("{}：{}".format(p["label"], p["text"]) if p.get("label") else p["text"])
                for p in o.get("points") or []
            ),
        }
        for o in outline
    ]

    return {
        "title": title,
        "overview": overview,
        "outline": outline,
        "highlights": highlights,
        "conclusion": conclusion,
        "summary": overview,
        "chapters": legacy_chapters,
        "highlight_lines": legacy_highlights,
    }


def build_mindmap(title: str, outline: List[Dict[str, Any]], highlights: List[Dict[str, str]]) -> Dict[str, Any]:
    """Build mindmap tree. Timeline stamps stay in outline.start — never in node labels."""

    def clean_label(text: str, max_len: int = 72) -> str:
        s = _as_str(text)
        # Strip markdown emphasis left in model / MD parse output
        s = re.sub(r"`+", "", s)
        s = s.replace("**", "").replace("__", "")
        s = s.replace("*", "")
        # Strip timeline: (00:00) （01:10） [03:25] 【04:00】
        s = re.sub(
            r"\s*[（(\[【]\s*\d{1,2}:\d{2}(?::\d{2})?\s*[）)\]】]\s*",
            " ",
            s,
        )
        s = re.sub(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s*[-–—:：]\s*", "", s)
        s = re.sub(r"\s+", " ", s).strip(" -–—:：|")
        if not s:
            return ""
        return s if len(s) <= max_len else s[: max_len - 1] + "…"

    children: List[Dict[str, Any]] = []
    for o in outline or []:
        pts = []
        for p in (o.get("points") or [])[:5]:
            label = clean_label(_as_str(p.get("label")), 24)
            text = clean_label(_as_str(p.get("text")), 72)
            name = "{}: {}".format(label, text) if label and text else (text or label)
            if name:
                pts.append({"name": name, "children": []})
        chapter = clean_label(_as_str(o.get("title")) or "章节", 40)
        children.append({"name": chapter or "章节", "children": pts})
    if highlights:
        children.append(
            {
                "name": "核心要点",
                "children": [
                    {
                        "name": clean_label(
                            _as_str(h.get("title")) or _as_str(h.get("text")),
                            40,
                        )
                        or "要点",
                        "children": [],
                    }
                    for h in highlights[:7]
                ],
            }
        )
    root_name = clean_label(title or "视频总结", 48) or "视频总结"
    return {"name": root_name, "children": children}


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise YtdlpError("模型返回为空", status_code=502)
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    raise YtdlpError("模型返回无法解析为 JSON", status_code=502)


def _section_body(md: str, heading: str) -> str:
    pattern = re.compile(
        r"^##\s*{}\s*\n([\s\S]*?)(?=^##\s|\Z)".format(re.escape(heading)),
        re.M,
    )
    m = pattern.search(md or "")
    return (m.group(1).strip() if m else "")


def _parse_outline_md(body: str) -> List[Dict[str, Any]]:
    outline: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for raw in (body or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
# also strip [] timestamps from markdown outline titles
        m_item = re.match(
            r"^\s*(\d+)[\.、]\s*\*{0,2}(.+?)\*{0,2}\s*"
            r"(?:[（(\[【](\d{1,2}:\d{2}(?::\d{2})?)[)）\]】])?\s*$",
            line,
        )
        if m_item:
            title = m_item.group(2).strip().strip("*").strip()
            start = m_item.group(3) or "00:00"
            current = {
                "title": title,
                "start": start,
                "start_sec": _parse_start_to_sec(start),
                "points": [],
            }
            outline.append(current)
            continue
        m_bullet = re.match(r"^\s*[-*•]\s+(.+)$", line)
        if m_bullet and current is not None:
            text = m_bullet.group(1).strip()
            m_lab = re.match(r"^\*{0,2}([^*:：]+)\*{0,2}\s*[:：]\s*(.+)$", text)
            if m_lab:
                current["points"].append({"label": m_lab.group(1).strip(), "text": m_lab.group(2).strip()})
            else:
                current["points"].append({"label": "", "text": text.strip("*").strip()})
    return outline


def _parse_highlights_md(body: str) -> List[Dict[str, str]]:
    highlights: List[Dict[str, str]] = []
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\d+[\.、]\s*", "", line)
        line = re.sub(r"^[-*•]\s+", "", line)
        m = re.match(r"^\*{0,2}([^*:：]+)\*{0,2}\s*[:：]\s*(.+)$", line)
        if m:
            highlights.append({"title": m.group(1).strip(), "text": m.group(2).strip()})
        else:
            text = line.strip("*").strip()
            if text:
                highlights.append({"title": "要点", "text": text})
    return highlights[:8]


def parse_summary_markdown(md: str, title: str) -> Dict[str, Any]:
    """Best-effort parse of streamed/partial Markdown into structured summary."""
    overview = _section_body(md, "视频概述")
    outline_body = _section_body(md, "内容大纲")
    highlights_body = _section_body(md, "核心知识要点")
    conclusion = _section_body(md, "总结")
    data = {
        "overview": overview,
        "outline": _parse_outline_md(outline_body),
        "highlights": _parse_highlights_md(highlights_body),
        "conclusion": conclusion,
    }
    # While streaming, do not force-fill empty later sections yet
    result = {
        "title": title,
        "overview": overview,
        "outline": data["outline"],
        "highlights": data["highlights"],
        "conclusion": conclusion,
        "summary": overview,
        "chapters": [],
        "stream_markdown": md,
    }
    return result


def finalize_summary_markdown(md: str, title: str) -> Dict[str, Any]:
    partial = parse_summary_markdown(md, title)
    return _normalize_result(
        {
            "overview": partial.get("overview"),
            "outline": partial.get("outline"),
            "highlights": partial.get("highlights"),
            "conclusion": partial.get("conclusion"),
        },
        title,
    )


def _chat(title: str, transcript: str, use_json_object: bool) -> str:
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": "视频标题：{}\n\n带时间戳字幕：\n{}".format(title, transcript),
        },
    ]
    kwargs: Dict[str, Any] = {
        "model": LLM_MODEL,
        "temperature": 0.3,
        "messages": messages,
    }
    if use_json_object:
        kwargs["response_format"] = {"type": "json_object"}
    completion = _client().chat.completions.create(**kwargs)
    return (completion.choices[0].message.content or "") if completion.choices else ""


def summarize_transcript(title: str, transcript: str) -> Dict[str, Any]:
    if not LLM_API_KEY:
        raise YtdlpError(
            "未配置 LLM_API_KEY（或 DEEPSEEK_API_KEY），无法生成 AI 总结。",
            status_code=503,
        )

    try:
        content = _chat(title, transcript, use_json_object=True)
    except AuthenticationError as exc:
        logger.warning("LLM auth failed: %s", exc)
        raise YtdlpError("LLM API 鉴权失败，请检查 LLM_API_KEY / DEEPSEEK_API_KEY。", status_code=503)
    except APIConnectionError as exc:
        logger.warning("LLM connection failed: %s", exc)
        raise YtdlpError("无法连接大模型服务，请检查 LLM_BASE_URL 与网络。", status_code=502)
    except APIError as exc:
        logger.warning("LLM APIError: %s", exc)
        try:
            content = _chat(title, transcript, use_json_object=False)
        except Exception as retry_exc:
            logger.warning("LLM retry failed: %s", retry_exc)
            raise YtdlpError("调用大模型失败，请稍后重试。", status_code=502) from retry_exc
    except Exception as exc:
        logger.exception("LLM unexpected error")
        raise YtdlpError("调用大模型失败：{}".format(exc), status_code=502) from exc

    data = _extract_json(content)
    return _normalize_result(data, title)


def summarize_transcript_streaming(
    title: str,
    transcript: str,
    on_partial: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Stream Markdown notes; call on_partial(md, partial_result) as tokens arrive."""
    if not LLM_API_KEY:
        raise YtdlpError(
            "未配置 LLM_API_KEY（或 DEEPSEEK_API_KEY），无法生成 AI 总结。",
            status_code=503,
        )

    messages = [
        {"role": "system", "content": _STREAM_SYSTEM},
        {
            "role": "user",
            "content": "视频标题：{}\n\n带时间戳字幕：\n{}".format(title, transcript),
        },
    ]
    buf = []
    try:
        stream = _client().chat.completions.create(
            model=LLM_MODEL,
            temperature=0.3,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            if not delta:
                continue
            buf.append(delta)
            text = "".join(buf)
            if on_partial:
                on_partial(text, parse_summary_markdown(text, title))
    except AuthenticationError as exc:
        raise YtdlpError("LLM API 鉴权失败，请检查 LLM_API_KEY / DEEPSEEK_API_KEY。", status_code=503) from exc
    except APIConnectionError as exc:
        raise YtdlpError("无法连接大模型服务，请检查 LLM_BASE_URL 与网络。", status_code=502) from exc
    except Exception as exc:
        # Fallback to non-stream JSON path
        logger.warning("stream summarize failed, fallback: %s", exc)
        return summarize_transcript(title, transcript)

    text = "".join(buf).strip()
    if not text:
        return summarize_transcript(title, transcript)
    if on_partial:
        on_partial(text, parse_summary_markdown(text, title))
    final = finalize_summary_markdown(text, title)
    final["stream_markdown"] = text
    return final


def answer_question(
    title: str,
    transcript: str,
    question: str,
    summary_hint: str = "",
) -> str:
    if not LLM_API_KEY:
        raise YtdlpError("未配置 LLM_API_KEY，无法回答。", status_code=503)
    q = (question or "").strip()
    if not q:
        raise YtdlpError("请输入问题", status_code=400)
    # Keep context bounded
    ctx = transcript or ""
    if len(ctx) > 60000:
        ctx = ctx[:60000] + "\n…（字幕已截断）"
    user = "视频标题：{}\n\n".format(title)
    if summary_hint:
        user += "已有总结摘要：\n{}\n\n".format(summary_hint[:3000])
    user += "字幕：\n{}\n\n用户问题：{}".format(ctx, q)
    try:
        completion = _client().chat.completions.create(
            model=LLM_MODEL,
            temperature=0.3,
            messages=[
                {"role": "system", "content": _QA_SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        return (completion.choices[0].message.content or "").strip() or "暂时无法回答，请换个问法重试。"
    except AuthenticationError as exc:
        raise YtdlpError("LLM API 鉴权失败，请检查密钥。", status_code=503) from exc
    except Exception as exc:
        logger.warning("answer_question failed: %s", exc)
        raise YtdlpError("回答失败，请稍后重试。", status_code=502) from exc


def answer_question_streaming(
    title: str,
    transcript: str,
    question: str,
    summary_hint: str = "",
) -> Iterator[str]:
    if not LLM_API_KEY:
        raise YtdlpError("未配置 LLM_API_KEY，无法回答。", status_code=503)
    q = (question or "").strip()
    if not q:
        raise YtdlpError("请输入问题", status_code=400)
    ctx = transcript or ""
    if len(ctx) > 60000:
        ctx = ctx[:60000] + "\n…（字幕已截断）"
    user = "视频标题：{}\n\n".format(title)
    if summary_hint:
        user += "已有总结摘要：\n{}\n\n".format(summary_hint[:3000])
    user += "字幕：\n{}\n\n用户问题：{}".format(ctx, q)
    try:
        stream = _client().chat.completions.create(
            model=LLM_MODEL,
            temperature=0.3,
            messages=[
                {"role": "system", "content": _QA_SYSTEM},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            if delta:
                yield delta
    except AuthenticationError as exc:
        raise YtdlpError("LLM API 鉴权失败，请检查密钥。", status_code=503) from exc
    except Exception as exc:
        logger.warning("answer_question_streaming failed: %s", exc)
        raise YtdlpError("回答失败，请稍后重试。", status_code=502) from exc
