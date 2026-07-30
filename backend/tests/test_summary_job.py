# -*- coding: utf-8 -*-
"""End-to-end summary job with mocked subtitle + LLM."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_summary_job_happy_path():
    fake_sub = {
        "title": "测试视频",
        "language": "zh",
        "source": "manual",
        "cues": [{"start_sec": 0, "start": "00:00", "text": "你好"}],
        "transcript": "[00:00] 你好世界，这是一段关于机器学习的讲解。",
        "webpage_url": "https://www.bilibili.com/video/BVtest",
    }
    fake_summary = {
        "title": "测试视频",
        "overview": "本视频介绍机器学习基础。",
        "conclusion": "建议按章节回看并动手练习。",
        "highlights": [
            {"title": "监督学习", "text": "用标注数据训练模型"},
            {"title": "模型训练", "text": "迭代优化参数"},
        ],
        "outline": [
            {
                "start": "00:00",
                "start_sec": 0,
                "title": "开场",
                "points": [{"label": "主题", "text": "引入机器学习"}],
            }
        ],
        "summary": "本视频介绍机器学习基础。",
        "chapters": [
            {
                "start": "00:00",
                "start_sec": 0,
                "title": "开场",
                "summary": "引入主题",
            }
        ],
        "stream_markdown": "## 视频概述\n本视频介绍机器学习基础。",
    }

    with mock.patch("app.summary_jobs.llm_configured", return_value=True), mock.patch(
        "app.summary_router.llm_configured", return_value=True
    ), mock.patch(
        "app.summary_jobs.fetch_subtitles", return_value=fake_sub
    ), mock.patch(
        "app.summary_jobs.summarize_transcript_streaming", return_value=fake_summary
    ):
        client = TestClient(app)
        r = client.post(
            "/api/summarize",
            json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"},
        )
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]

        result = None
        for _ in range(40):
            s = client.get("/api/summarize/{}".format(job_id))
            assert s.status_code == 200
            body = s.json()
            if body["status"] == "done":
                result = body["result"]
                break
            if body["status"] == "failed":
                raise AssertionError(body.get("error"))
            time.sleep(0.05)

        assert result is not None
        assert result["overview"] == "本视频介绍机器学习基础。"
        assert result["summary"] == "本视频介绍机器学习基础。"
        assert result["highlights"][0]["title"] == "监督学习"
        assert result["outline"][0]["title"] == "开场"
        assert result["conclusion"]
        assert result.get("cues") is not None
        assert result.get("mindmap") is not None
        assert result["mindmap"]["name"]
        assert result.get("transcript")


def test_health_download_core_clean():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "free_daily_parses" in data
    assert "llm_configured" not in data
    assert "free_daily_summaries" not in data


def test_summary_meta():
    client = TestClient(app)
    r = client.get("/api/summary/meta")
    assert r.status_code == 200
    data = r.json()
    assert "llm_configured" in data
    assert "free_daily_summaries" in data


if __name__ == "__main__":
    test_health_download_core_clean()
    test_summary_meta()
    test_summary_job_happy_path()
    print("ok")
