"""Codex token 元数据解析回归测试。"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from app.collectors.codex import CodexCollector
from app.db.history import HistoryRepository


def test_parse_token_count_without_reading_message_content() -> None:
    collector = CodexCollector(Path("missing"))
    rows = [
        {"type": "turn_context", "payload": {"model": "gpt-test"}},
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 1_000,
                        "cached_input_tokens": 600,
                        "output_tokens": 200,
                        "reasoning_output_tokens": 80,
                        "total_tokens": 1_200,
                    },
                    "last_token_usage": {"input_tokens": 480},
                    "model_context_window": 32_000,
                },
            },
        },
    ]

    snapshot = collector._parse_rows(rows, sessions_today=3)

    assert snapshot.model == "gpt-test"
    assert snapshot.total_tokens == 1_200
    assert snapshot.cached_tokens == 600
    assert snapshot.context_used == 480
    assert snapshot.context_size == 32_000
    assert snapshot.sessions_today == 3


def test_find_recent_model_outside_regular_tail_window(tmp_path: Path) -> None:
    session_file = tmp_path / "rollout.jsonl"
    session_file.write_text(
        '{"type":"turn_context","payload":{"model":"gpt-long-session"}}\n'
        + '{"type":"event_msg","payload":{"type":"token_count"}}\n' * 20,
        encoding="utf-8",
    )
    collector = CodexCollector(tmp_path, tail_bytes=64)

    assert collector._find_recent_model(session_file) == "gpt-long-session"


def _token_row(timestamp: datetime, last_total: int, session_total: int) -> str:
    """构造仅包含数值元数据的 token_count 测试行。"""

    payload = {
        "timestamp": timestamp.isoformat(),
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": session_total - 20,
                    "output_tokens": 20,
                    "total_tokens": session_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 10,
                    "cached_input_tokens": max(0, last_total - 30),
                    "output_tokens": 10,
                    "reasoning_output_tokens": 4,
                    "total_tokens": last_total,
                },
                "model_context_window": 128_000,
            },
        },
    }
    return json.dumps(payload) + "\n"


def test_collect_aggregates_daily_usage_across_sessions_and_restarts(
    tmp_path: Path,
) -> None:
    """每日总量应跨 session 求和，增量轮询和进程重启都不能重复或回退。"""

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    now = datetime.now().astimezone()
    yesterday = now - timedelta(days=1)
    first = sessions / "first.jsonl"
    second = sessions / "second.jsonl"
    first.write_text(
        _token_row(yesterday, 700, 700) + _token_row(now, 1_000, 1_700),
        encoding="utf-8",
    )
    second.write_text(_token_row(now, 2_000, 2_000), encoding="utf-8")

    collector = CodexCollector(tmp_path)
    initial = collector._collect_sync()
    assert initial.total_tokens == 3_000
    assert initial.previous_day_tokens == 700
    assert initial.tokens_7d == 3_700
    assert initial.tokens_30d == 3_700
    assert initial.sessions_today == 2
    assert initial.range_usage["24H"].total_tokens == 3_000
    assert initial.range_usage["7D"].total_tokens == 3_700
    assert initial.range_usage["7D"].interactions == 2

    # 增量：第二次只处理追加行，已有的 3,000 token 不会再次计数。
    with second.open("a", encoding="utf-8") as handle:
        handle.write(_token_row(now, 500, 2_500))
    updated = collector._collect_sync()
    assert updated.total_tokens == 3_500

    # 重启：新实例从 JSONL 重建相同日累计，不依赖进程内旧状态。
    restarted = CodexCollector(tmp_path)._collect_sync()
    assert restarted.total_tokens == 3_500
    assert restarted.previous_day_tokens == 700
    assert restarted.tokens_7d == 4_200


def test_collect_marks_only_recent_codex_session_active(tmp_path: Path) -> None:
    """旧 session 仍可统计，但只有近期写入才代表 Codex 正在运行。"""

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    session = sessions / "rollout.jsonl"
    now = datetime.now().astimezone()
    session.write_text(_token_row(now, 100, 100), encoding="utf-8")
    collector = CodexCollector(tmp_path, active_window_seconds=10)

    assert collector._collect_sync().status == "active"

    stale = time.time() - 60
    os.utime(session, (stale, stale))
    assert collector._collect_sync().status == "idle"


def test_repeated_usage_deduplicated_but_equal_cost_requests_count(tmp_path: Path) -> None:
    """同累计通知重复不增加用量，新响应累计递增则正常计入。"""

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    now = datetime.now().astimezone()
    first = _token_row(now, 100, 100)
    repeated = _token_row(now + timedelta(milliseconds=1), 100, 100)
    next_request = _token_row(now + timedelta(milliseconds=2), 100, 200)
    (sessions / "test.jsonl").write_text(first + first + repeated + next_request, encoding="utf-8")
    collector = CodexCollector(tmp_path)
    assert collector._collect_sync().total_tokens == 200
    assert collector.usage_audit() == {
        "raw_tokens": 400, "accepted_tokens": 200, "duplicate_tokens": 200, "duplicate_events": 2,
    }
    assert collector._collect_sync().total_tokens == 200
    assert CodexCollector(tmp_path)._collect_sync().total_tokens == 200


def test_archive_move_preserves_usage_without_duplicate_session(tmp_path: Path) -> None:
    """归档移动与同时存在的副本都应保持同一事件、同一会话只计一次。"""

    sessions = tmp_path / "sessions"
    archive = tmp_path / "archived_sessions"
    sessions.mkdir()
    archive.mkdir()
    now = datetime.now().astimezone()
    source = sessions / "test.jsonl"
    source.write_text(_token_row(now, 100, 100), encoding="utf-8")
    collector = CodexCollector(tmp_path)
    assert collector._collect_sync().total_tokens == 100
    target = archive / source.name
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    assert collector._collect_sync().total_tokens == 100
    source.unlink()
    snapshot = collector._collect_sync()
    assert snapshot.total_tokens == 100
    assert snapshot.sessions_today == 1
    assert snapshot.status == "idle"


def test_persisted_ledger_keeps_usage_after_source_file_is_deleted(tmp_path: Path) -> None:
    """已采集的匿名事件应独立于 JSONL 源文件，避免清理日志后历史总量回退。"""

    codex_home = tmp_path / "codex"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    now = datetime.now().astimezone()
    source = sessions / "persisted.jsonl"
    source.write_text(_token_row(now, 120, 120), encoding="utf-8")
    repository = HistoryRepository(tmp_path / "neurodeck.db")
    repository.initialize()

    first = CodexCollector(codex_home, history_repository=repository)._collect_sync()
    source.unlink()
    restored = CodexCollector(codex_home, history_repository=repository)._collect_sync()

    assert first.total_tokens == 120
    assert restored.total_tokens == 120
    assert restored.range_usage["24H"].total_tokens == 120


def test_collector_persists_anonymous_workspace_and_model_metadata(tmp_path: Path) -> None:
    """账本允许显示项目末级目录名，但不得保存完整路径或原始会话 ID。"""

    codex_home = tmp_path / "codex"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    now = datetime.now().astimezone()
    raw_session_id = "private-session-id"
    raw_workspace = "E:\\Private\\Clients\\NeuroDeck"
    metadata = [
        {
            "timestamp": now.isoformat(),
            "type": "session_meta",
            "payload": {"id": raw_session_id, "cwd": raw_workspace},
        },
        {
            "timestamp": now.isoformat(),
            "type": "turn_context",
            "payload": {"model": "gpt-private", "cwd": raw_workspace},
        },
    ]
    source = sessions / "metadata.jsonl"
    source.write_text(
        "".join(json.dumps(row) + "\n" for row in metadata)
        + _token_row(now, 120, 120),
        encoding="utf-8",
    )
    database_path = tmp_path / "neurodeck.db"
    repository = HistoryRepository(database_path)
    repository.initialize()

    CodexCollector(codex_home, history_repository=repository)._collect_sync()

    import sqlite3

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT session_id, model, workspace_id, workspace_label, activity_tokens FROM codex_usage_events"
        ).fetchone()
    assert row[0] != raw_session_id
    assert row[1] == "gpt-private"
    assert row[2] and raw_workspace not in row[2]
    assert row[3] == "NeuroDeck"
    assert row[4] == 120
