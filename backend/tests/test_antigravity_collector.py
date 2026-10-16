"""Antigravity token 元数据与多模型解析回归测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.collectors.antigravity import AntigravityCollector, _humanize_model
from app.db.history import HistoryRepository


def test_humanize_model() -> None:
    assert _humanize_model("MODEL_PLACEHOLDER_M35") == "Claude Sonnet 4.6 (Thinking)"
    assert _humanize_model("MODEL_PLACEHOLDER_M318") == "Gemini 3.8"
    assert _humanize_model("Gemini 3.8 Flash (High)") == "Gemini 3.8"
    assert _humanize_model("Gemini 3.8 Flash") == "Gemini 3.8"
    assert _humanize_model("flash") == "Gemini Flash"
    assert _humanize_model("flash_lite") == "Gemini Flash Lite"
    assert _humanize_model("pro") == "Gemini Pro"
    assert _humanize_model("custom_model") == "model"
    assert _humanize_model("standard") == "standard"


import asyncio


def test_antigravity_collector_reads_transcripts_and_models(tmp_path: Path) -> None:
    async def run_test() -> None:
        brain_dir = tmp_path / "brain"
        conv_id = "test-conv-12345"
        logs_dir = brain_dir / conv_id / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)

        # 写入 state 文件
        state_file = tmp_path / "antigravity_state.pbtxt"
        state_file.write_text("last_selected_agent_model: MODEL_PLACEHOLDER_M318\n", encoding="utf-8")

        now = datetime.now(timezone.utc)
        transcript_file = logs_dir / "transcript.jsonl"
        lines = [
            json.dumps({
                "step_index": 0,
                "source": "USER",
                "type": "USER_INPUT",
                "created_at": now.isoformat(),
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` from None to Gemini 3.8 Flash (High).\n</USER_SETTINGS_CHANGE>",
            }),
            json.dumps({
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": now.isoformat(),
                "input_tokens": 1000,
                "cache_read_tokens": 200,
                "output_tokens": 150,
            }),
            json.dumps({
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": now.isoformat(),
                "input_tokens": 500,
                "cache_read_tokens": 100,
                "output_tokens": 50,
            }),
        ]
        transcript_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        db_path = tmp_path / "neurodeck.db"
        repo = HistoryRepository(db_path)
        repo.initialize()

        collector = AntigravityCollector(tmp_path, history_repository=repo)
        snapshot = await collector.collect()

        assert snapshot.provider == "antigravity"
        assert snapshot.online is True
        assert snapshot.model == "Gemini 3.8"
        assert snapshot.total_tokens == 2000  # (1000+150+200) + (500+50+100)
        assert snapshot.input_tokens == 1500
        assert snapshot.output_tokens == 200
        assert snapshot.cached_tokens == 300
        assert snapshot.sessions_today == 1

        # 验证审计与去重
        audit = collector.usage_audit(days=1)
        assert audit["raw_tokens"] == 2000
        assert audit["accepted_tokens"] == 2000
        assert audit["duplicate_tokens"] == 0

        # 再次 collect 保持幂等
        snapshot2 = await collector.collect()
        assert snapshot2.total_tokens == 2000

        # 检查数据库记录
        summary = repo.get_antigravity_usage_summary()
        assert summary.range_usage["24H"].total_tokens == 2000
        assert summary.range_usage["24H"].input_tokens == 1500
        assert summary.range_usage["24H"].output_tokens == 200

    asyncio.run(run_test())


def test_antigravity_collector_state_model_precedence_over_transcript(tmp_path: Path) -> None:
    """验证 IDE 状态文件中的实时模型优先于历史 transcript 中的旧设置。"""
    async def run_test() -> None:
        brain_dir = tmp_path / "brain"
        conv_id = "test-conv-priority"
        logs_dir = brain_dir / conv_id / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)

        # IDE state 中选中的是 Gemini 3.8
        state_file = tmp_path / "antigravity_state.pbtxt"
        state_file.write_text("last_selected_agent_model: MODEL_PLACEHOLDER_M318\n", encoding="utf-8")

        now = datetime.now(timezone.utc)
        transcript_file = logs_dir / "transcript.jsonl"
        # 历史 transcript 记录的旧设置是 Claude Sonnet 4.6 (Thinking)
        lines = [
            json.dumps({
                "step_index": 0,
                "source": "USER",
                "type": "USER_INPUT",
                "created_at": now.isoformat(),
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` from None to Claude Sonnet 4.6 (Thinking).\n</USER_SETTINGS_CHANGE>",
            }),
            json.dumps({
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": now.isoformat(),
                "input_tokens": 100,
                "output_tokens": 50,
            }),
        ]
        transcript_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        collector = AntigravityCollector(tmp_path)
        snapshot = await collector.collect()

        assert snapshot.model == "Gemini 3.8"

    asyncio.run(run_test())


def test_antigravity_collector_fallback_to_session_when_state_missing(tmp_path: Path) -> None:
    """当缺少 state 文件时，正确回退到会话记录的模型设置。"""
    async def run_test() -> None:
        brain_dir = tmp_path / "brain"
        conv_id = "test-conv-fallback"
        logs_dir = brain_dir / conv_id / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)

        now = datetime.now(timezone.utc)
        transcript_file = logs_dir / "transcript.jsonl"
        lines = [
            json.dumps({
                "step_index": 0,
                "source": "USER",
                "type": "USER_INPUT",
                "created_at": now.isoformat(),
                "content": "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` from None to Claude Sonnet 4.6 (Thinking).\n</USER_SETTINGS_CHANGE>",
            }),
            json.dumps({
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": now.isoformat(),
                "input_tokens": 100,
                "output_tokens": 50,
            }),
        ]
        transcript_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        collector = AntigravityCollector(tmp_path)
        snapshot = await collector.collect()

        assert snapshot.model == "Claude Sonnet 4.6 (Thinking)"

    asyncio.run(run_test())


def test_antigravity_collector_handles_missing_home(tmp_path: Path) -> None:
    async def run_test() -> None:
        non_existent = tmp_path / "missing"
        collector = AntigravityCollector(non_existent)
        snapshot = await collector.collect()

        assert snapshot.provider == "antigravity"
        assert snapshot.online is False
        assert snapshot.status == "offline"

    asyncio.run(run_test())
