"""SQLite 历史持久化与聚合回归测试。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.db.history import HistoryRepository
from app.schemas.dashboard import CodexUsageEvent, OllamaUsageEvent, SignalEvent, TrendPoint


def _point(timestamp: datetime, tokens: int, cpu: float) -> TrendPoint:
    """构造不包含用户内容的确定性测试指标。"""

    return TrendPoint(
        timestamp=timestamp,
        ollama_tokens=tokens // 2,
        codex_tokens=tokens,
        ollama_tokens_per_second=12.5,
        cpu_usage=cpu,
        gpu_usage=cpu + 10,
        gpu_temperature_c=60 + cpu / 10,
        ram_usage=40,
        vram_usage=50,
    )


def test_history_survives_repository_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "neurodeck.db"
    repository = HistoryRepository(database_path)
    repository.initialize()
    timestamp = datetime.now(timezone.utc)
    repository.save_sample(
        _point(timestamp, 1_200, 20),
        [
            SignalEvent(
                timestamp=timestamp,
                source="CODEX",
                event="TOKEN UPDATE",
                detail="+1,200 tokens",
            )
        ],
    )

    reopened = HistoryRepository(database_path)
    reopened.initialize()

    history = reopened.query_history("24H")
    signals = reopened.load_recent_signals()
    assert history[-1].codex_tokens == 1_200
    assert signals[0].detail == "+1,200 tokens"


def test_signals_can_persist_without_creating_history_sample(tmp_path: Path) -> None:
    """实时状态事件落盘不应强制生成一个额外趋势点。"""

    repository = HistoryRepository(tmp_path / "signals.db")
    repository.initialize()
    repository.save_signals(
        [SignalEvent(source="OLLAMA", event="CONNECTED", detail="qwen-test")]
    )

    assert repository.query_history("24H") == []
    assert repository.load_recent_signals()[0].event == "CONNECTED"


def test_repository_initializes_schema_version(tmp_path: Path) -> None:
    """数据库必须保留显式版本，为后续非破坏迁移提供判断依据。"""

    import sqlite3

    database_path = tmp_path / "versioned.db"
    repository = HistoryRepository(database_path)
    repository.initialize()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6


def test_repository_migrates_v5_codex_activity_column_without_losing_usage(tmp_path: Path) -> None:
    """v5 账本升级后保留历史实际用量，并允许后续日志重扫补齐活动快照。"""

    import sqlite3

    database_path = tmp_path / "v5.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE codex_usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                model TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                workspace_label TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cached_tokens INTEGER NOT NULL,
                reasoning_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """INSERT INTO codex_usage_events (
                timestamp, event_id, session_id, model, workspace_id, workspace_label,
                input_tokens, output_tokens, cached_tokens, reasoning_tokens, total_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), "old-event", "session", "gpt-test", "", "", 90, 10, 0, 0, 100),
        )
        connection.execute("PRAGMA user_version = 5")

    repository = HistoryRepository(database_path)
    repository.initialize()
    repository.save_codex_usage([CodexUsageEvent(
        event_id="old-event", session_id="session", total_tokens=100, activity_tokens=1_500,
    )])

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT total_tokens, activity_tokens FROM codex_usage_events WHERE event_id = 'old-event'"
        ).fetchone()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert row == (100, 1_500)
    assert version == 6


def test_history_uses_last_token_value_and_average_metrics(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "aggregate.db")
    repository.initialize()
    now = datetime.now(timezone.utc)
    bucket_start = now.replace(
        minute=(now.minute // 30) * 30,
        second=0,
        microsecond=0,
    ) - timedelta(minutes=30)
    points = [
        _point(bucket_start + timedelta(minutes=1), 100, 10),
        _point(bucket_start + timedelta(minutes=5), 200, 20),
        _point(bucket_start + timedelta(minutes=10), 300, 30),
    ]
    for point in points:
        repository.save_sample(point, [])

    history = repository.query_history("7D")

    assert len(history) == 1
    assert history[0].codex_tokens == 300
    assert history[0].cpu_usage == pytest.approx(20)
    assert history[0].gpu_temperature_c == pytest.approx(62)


def test_ollama_usage_summary_contains_only_numeric_metrics(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "ollama.db")
    repository.initialize()
    repository.save_ollama_usage(
        OllamaUsageEvent(
            request_id="req-1",
            endpoint="/api/chat",
            model="qwen-test",
            prompt_tokens=40,
            completion_tokens=10,
            total_duration_ns=2_000_000_000,
            eval_duration_ns=500_000_000,
            tokens_per_second=20,
        )
    )

    summary = repository.get_ollama_usage_summary()

    assert summary.model == "qwen-test"
    assert summary.total_tokens == 50
    assert summary.tokens_per_second == 20
    assert summary.context_used == 40
    assert summary.requests_today == 1
    assert summary.completed_requests_today == 1
    assert summary.tokens_7d == 50
    assert summary.tokens_30d == 50
    assert summary.range_usage["24H"].input_tokens == 40
    assert summary.range_usage["24H"].output_tokens == 10
    assert summary.range_usage["7D"].interactions == 1


def test_ollama_usage_summary_uses_local_calendar_ranges(tmp_path: Path) -> None:
    """Ollama 今日、7 天与 30 天合计必须随自然日范围增长。"""

    repository = HistoryRepository(tmp_path / "ollama-ranges.db")
    repository.initialize()
    local_now = datetime.now().astimezone()
    events = [
        ("today", local_now, 10),
        ("week", local_now - timedelta(days=3), 20),
        ("month", local_now - timedelta(days=12), 30),
    ]
    for request_id, timestamp, tokens in events:
        repository.save_ollama_usage(
            OllamaUsageEvent(
                timestamp=timestamp,
                request_id=request_id,
                endpoint="/api/chat",
                model="qwen-test",
                prompt_tokens=tokens,
                completion_tokens=0,
            )
        )

    summary = repository.get_ollama_usage_summary()

    assert summary.total_tokens == 10
    assert summary.tokens_7d == 30
    assert summary.tokens_30d == 60
    assert summary.range_usage["7D"].input_tokens == 30
    assert summary.range_usage["30D"].input_tokens == 60
    assert summary.range_usage["24H"].interactions == 1


def test_ollama_summary_counts_attempts_but_only_totals_exact_completions(tmp_path: Path) -> None:
    """详情请求数不能漏掉失败/未计量调用，Token 与完成事件仍只使用精确响应。"""

    repository = HistoryRepository(tmp_path / "ollama-outcomes.db")
    repository.initialize()
    now = datetime.now(timezone.utc)
    events = [
        OllamaUsageEvent(timestamp=now, request_id="exact", endpoint="/api/chat", model="exact-model",
                         prompt_tokens=8, completion_tokens=2),
        OllamaUsageEvent(timestamp=now, request_id="failed", endpoint="/api/chat", model="failed-model",
                         status="failed", metric_precision="unavailable", prompt_tokens=999),
        OllamaUsageEvent(timestamp=now, request_id="unmetered", endpoint="/api/chat", model="latest-model",
                         status="unmetered", metric_precision="unavailable"),
    ]
    for event in events:
        repository.save_ollama_usage(event)

    summary = repository.get_ollama_usage_summary()

    assert summary.requests_today == 3
    assert summary.completed_requests_today == 1
    assert summary.total_tokens == 10
    assert summary.model == "latest-model"


def test_future_usage_cannot_change_current_summary(tmp_path: Path) -> None:
    """系统时钟异常产生的未来记录不能污染当前模型、上下文或区间用量。"""

    repository = HistoryRepository(tmp_path / "ollama-future.db")
    repository.initialize()
    repository.save_ollama_usage(OllamaUsageEvent(
        timestamp=datetime.now(timezone.utc), request_id="current", endpoint="/api/chat",
        model="current-model", prompt_tokens=12, tokens_per_second=20,
    ))
    repository.save_ollama_usage(OllamaUsageEvent(
        timestamp=datetime.now(timezone.utc) + timedelta(days=1), request_id="future",
        endpoint="/api/chat", model="future-model", prompt_tokens=10_000, tokens_per_second=999,
    ))

    summary = repository.get_ollama_usage_summary()
    assert summary.model == "current-model"
    assert summary.total_tokens == 12
    assert summary.context_used == 12
    assert summary.tokens_per_second == 20
    assert summary.requests_today == 1
    assert [row["request_id"] for row in repository.query_ollama_requests()] == ["current"]


def test_codex_ledger_is_idempotent_and_drives_range_summary(tmp_path: Path) -> None:
    """Codex 事件重放不能重复，输入/输出/缓存等分项必须来自同一持久化账本。"""

    repository = HistoryRepository(tmp_path / "codex-ledger.db")
    repository.initialize()
    now = datetime.now(timezone.utc)
    event = CodexUsageEvent(
        timestamp=now,
        event_id="event-1",
        session_id="anonymous-session",
        model="gpt-test",
        input_tokens=90,
        output_tokens=10,
        cached_tokens=40,
        reasoning_tokens=3,
        total_tokens=100,
        activity_tokens=1_200,
    )
    repository.save_codex_usage([event, event])

    summary = repository.get_codex_usage_summary()

    assert summary.model == "gpt-test"
    assert summary.range_usage["24H"].total_tokens == 100
    assert summary.range_usage["24H"].input_tokens == 90
    assert summary.range_usage["24H"].cached_tokens == 40
    assert summary.range_usage["24H"].interactions == 1
    assert summary.range_usage["24H"].exact_completions == 1

    # 对账字段必须幂等保存，但不能混入实际用量汇总。
    import sqlite3
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute(
            "SELECT activity_tokens FROM codex_usage_events WHERE event_id = ?", ("event-1",)
        ).fetchone()[0] == 1_200


def test_token_volume_uses_exact_events_and_fills_empty_buckets(tmp_path: Path) -> None:
    """柱状图只汇总精确事件，并为今天尚无活动的小时保留零值桶。"""

    repository = HistoryRepository(tmp_path / "token-volume.db")
    repository.initialize()
    now = datetime.now(timezone.utc)
    repository.save_codex_usage([
        CodexUsageEvent(
            timestamp=now,
            event_id="codex-current",
            session_id="session",
            total_tokens=70,
        )
    ])
    repository.save_ollama_usage(OllamaUsageEvent(
        timestamp=now,
        request_id="ollama-current",
        endpoint="/api/chat",
        model="qwen-test",
        prompt_tokens=20,
        completion_tokens=10,
    ))
    repository.save_ollama_usage(OllamaUsageEvent(
        timestamp=now,
        request_id="ollama-failed",
        endpoint="/api/chat",
        model="qwen-test",
        prompt_tokens=999,
        status="failed",
        metric_precision="unavailable",
    ))

    buckets = repository.query_token_volume("24H")

    assert len(buckets) == now.astimezone().hour + 1
    assert sum(bucket.codex_tokens for bucket in buckets) == 70
    assert sum(bucket.ollama_tokens for bucket in buckets) == 30


def test_token_activity_rebuilds_exact_cumulative_range(tmp_path: Path) -> None:
    """累计曲线末点必须等于精确账本合计，失败请求不能进入序列。"""

    repository = HistoryRepository(tmp_path / "token-activity.db")
    repository.initialize()
    now = datetime.now(timezone.utc)
    repository.save_codex_usage([
        CodexUsageEvent(
            timestamp=now - timedelta(minutes=6),
            event_id="codex-earlier",
            session_id="session",
            total_tokens=40,
        ),
        CodexUsageEvent(
            timestamp=now,
            event_id="codex-current",
            session_id="session",
            total_tokens=60,
        ),
    ])
    repository.save_ollama_usage(OllamaUsageEvent(
        timestamp=now,
        request_id="ollama-current",
        endpoint="/api/chat",
        model="qwen-test",
        prompt_tokens=20,
        completion_tokens=10,
    ))
    repository.save_ollama_usage(OllamaUsageEvent(
        timestamp=now,
        request_id="ollama-failed",
        endpoint="/api/chat",
        model="qwen-test",
        prompt_tokens=999,
        status="failed",
        metric_precision="unavailable",
    ))

    points = repository.query_token_activity("24H")

    assert points[0].ollama_tokens == 0
    assert points[0].codex_tokens == 0
    assert points[-1].ollama_tokens == 30
    assert points[-1].codex_tokens == 100
    assert points[-1].timestamp <= datetime.now(timezone.utc)
    assert all(
        current.codex_tokens >= previous.codex_tokens
        and current.ollama_tokens >= previous.ollama_tokens
        for previous, current in zip(points, points[1:])
    )
