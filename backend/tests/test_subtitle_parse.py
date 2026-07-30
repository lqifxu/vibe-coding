# -*- coding: utf-8 -*-
"""Unit tests for subtitle parsing (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.subtitle_service import (  # noqa: E402
    cues_to_srt,
    cues_to_transcript,
    cues_to_vtt,
    export_subtitles,
    parse_vtt_or_srt,
)


SAMPLE_VTT = """WEBVTT

00:00:00.000 --> 00:00:02.500
大家好，欢迎来到本期讲解。

00:00:02.500 --> 00:00:05.000
今天我们讨论机器学习的基础概念。

00:01:10.000 --> 00:01:15.000
首先是监督学习。
"""


def test_parse_vtt_basic():
    cues = parse_vtt_or_srt(SAMPLE_VTT)
    assert len(cues) == 3
    assert cues[0]["start"] == "00:00"
    assert "大家好" in cues[0]["text"]
    assert cues[2]["start_sec"] == 70


def test_dedupe_identical():
    raw = """WEBVTT

00:00:01.000 --> 00:00:02.000
重复字幕

00:00:02.000 --> 00:00:03.000
重复字幕

00:00:03.000 --> 00:00:04.000
下一句
"""
    cues = parse_vtt_or_srt(raw)
    assert len(cues) == 2
    assert cues[1]["text"] == "下一句"


def test_transcript_truncate():
    cues = [{"start": "00:00", "start_sec": 0, "text": "a" * 50} for _ in range(10)]
    out = cues_to_transcript(cues, max_chars=80)
    assert "截断" in out or len(out) <= 120


def test_cues_to_srt():
    cues = [
        {"start_sec": 0, "start": "00:00", "text": "第一句"},
        {"start_sec": 2.5, "start": "00:02", "text": "第二句"},
    ]
    srt = cues_to_srt(cues)
    assert "1\n" in srt
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert "第一句" in srt
    assert "00:00:02,500 -->" in srt
    assert "第二句" in srt


def test_cues_to_vtt():
    cues = [{"start_sec": 1.2, "start": "00:01", "text": "Hello"}]
    vtt = cues_to_vtt(cues)
    assert vtt.startswith("WEBVTT")
    assert "00:00:01.200 -->" in vtt
    assert "Hello" in vtt


def test_export_subtitles_formats():
    cues = [{"start_sec": 0, "start": "00:00", "text": "hi"}]
    body, mime, ext = export_subtitles(cues, "srt")
    assert ext == "srt" and "hi" in body and "subrip" in mime
    body, mime, ext = export_subtitles(cues, "vtt")
    assert ext == "vtt" and body.startswith("WEBVTT")
    body, mime, ext = export_subtitles(cues, "txt", transcript="[00:00] hi")
    assert ext == "txt" and body == "[00:00] hi"


if __name__ == "__main__":
    test_parse_vtt_basic()
    test_dedupe_identical()
    test_transcript_truncate()
    test_cues_to_srt()
    test_cues_to_vtt()
    test_export_subtitles_formats()
    print("ok")
