"""Codex 匿名账本多维分析回归测试。"""

from datetime import datetime, timedelta, timezone

from app.db.codex_analytics import query_codex_analytics
from app.db.history import HistoryRepository
from app.schemas.dashboard import CodexUsageEvent
from app.db import codex_analytics


def test_codex_analytics_groups_models_workspaces_and_sessions(tmp_path) -> None:
    """三个排行维度必须共享同一批事件，总量与缓存比例能够互相核对。"""

    repository = HistoryRepository(tmp_path / "codex-analytics.db")
    repository.initialize()
    now = datetime.now(timezone.utc)
    repository.save_codex_usage([
        CodexUsageEvent(
            timestamp=now,
            event_id="one",
            session_id="session-a",
            model="gpt-alpha",
            workspace_id="workspace-a",
            workspace_label="NeuroDeck",
            input_tokens=80,
            output_tokens=20,
            cached_tokens=40,
            reasoning_tokens=5,
            total_tokens=100,
            activity_tokens=1_000,
        ),
        CodexUsageEvent(
            timestamp=now,
            event_id="two",
            session_id="session-b",
            model="gpt-beta",
            workspace_id="workspace-b",
            workspace_label="Console",
            input_tokens=180,
            output_tokens=20,
            cached_tokens=90,
            reasoning_tokens=7,
            total_tokens=200,
            activity_tokens=2_000,
        ),
    ])

    analytics = query_codex_analytics(repository, "24H")

    assert analytics["summary"]["total_tokens"] == 300
    assert analytics["summary"]["sessions"] == 2
    assert analytics["summary"]["workspaces"] == 2
    assert analytics["summary"]["models"] == 2
    assert analytics["summary"]["cache_ratio"] == 50
    assert analytics["models"][0]["model"] == "gpt-beta"
    assert analytics["workspaces"][0]["workspace"] == "Console"
    assert analytics["sessions"][0]["session"] == "S-SESSION-"
    assert analytics["daily"][-1]["total_tokens"] == 300
    assert analytics["period_comparison"][0]["total_tokens"] == analytics["summary"]["total_tokens"]
    assert analytics["period_comparison"][0]["activity_tokens"] == 3_000
    assert analytics["period_comparison"][0]["activity_events"] == 2
    assert sum(item["total_tokens"] for item in analytics["timeline"]) == 300
    assert sum(item["total_tokens"] for item in analytics["activity_heatmap"]) == 300
    assert analytics["baseline_comparison"]["today_tokens"] == 300
    assert len(analytics["activity_heatmap"]) == 7 * 24
    assert datetime.fromisoformat(analytics["local_start"]) == datetime.fromisoformat(analytics["start"])


def test_codex_event_upsert_enriches_metadata_without_duplicate_tokens(tmp_path) -> None:
    """重扫旧日志可补齐模型和工作区，但不能让同一事件再次计费。"""

    repository = HistoryRepository(tmp_path / "codex-enrichment.db")
    repository.initialize()
    event = CodexUsageEvent(
        event_id="stable-event",
        session_id="anonymous-session",
        total_tokens=120,
    )
    repository.save_codex_usage([event])
    repository.save_codex_usage([
        event.model_copy(update={
            "model": "gpt-enriched",
            "workspace_id": "workspace-hash",
            "workspace_label": "NeuroDeck",
        })
    ])

    analytics = query_codex_analytics(repository, "24H")

    assert analytics["summary"]["total_tokens"] == 120
    assert analytics["models"][0]["model"] == "gpt-enriched"
    assert analytics["workspaces"][0]["workspace"] == "NeuroDeck"


def test_period_comparison_uses_explicit_boundaries_and_one_watermark(tmp_path, monkeypatch) -> None:
    """自然日、UTC 日与最近 24h 应有不同总量；未来事件和晚插入事件不能混入同批对账。"""

    repository = HistoryRepository(tmp_path / "periods.db")
    repository.initialize()
    now = datetime(2026, 9, 8, 2, tzinfo=timezone.utc)
    local_start = datetime(2026, 9, 7, 7, tzinfo=timezone.utc)
    monkeypatch.setattr(codex_analytics, "calendar_range_start", lambda *_args: local_start)
    samples = [
        (now - timedelta(hours=23), 100),
        (local_start, 25),
        (local_start + timedelta(hours=1), 200),
        (now - timedelta(hours=1), 300),
        (now + timedelta(hours=1), 999),
    ]
    repository.save_codex_usage([
        CodexUsageEvent(
            timestamp=timestamp,
            event_id=f"event-{index}",
            session_id="session",
            total_tokens=tokens,
            activity_tokens=tokens * 10,
        )
        for index, (timestamp, tokens) in enumerate(samples)
    ])
    with repository._connect() as connection:
        watermark = connection.execute("SELECT MAX(id) FROM codex_usage_events").fetchone()[0]
    repository.save_codex_usage([CodexUsageEvent(
        timestamp=now, event_id="late-insert", session_id="session", total_tokens=777,
    )])
    with repository._connect() as connection:
        comparison = codex_analytics._period_comparison(connection, repository, now, watermark)

    assert {item["period"]: item["total_tokens"] for item in comparison} == {
        "local_today": 525, "utc_today": 300, "rolling_24h": 625,
    }
    assert [item["events"] for item in comparison] == [3, 1, 4]
    assert {item["period"]: item["activity_tokens"] for item in comparison} == {
        "local_today": 5_250, "utc_today": 3_000, "rolling_24h": 6_250,
    }
    assert datetime.fromisoformat(comparison[0]["start"]) == local_start
    assert comparison[1]["start"] == "2026-09-08T00:00:00+00:00"


def test_period_comparison_keeps_empty_period_explicit(tmp_path) -> None:
    """成功查询空账本返回明确的零事件，不省略时间窗口或依赖前端伪造数值。"""

    repository = HistoryRepository(tmp_path / "empty-periods.db")
    repository.initialize()
    analytics = query_codex_analytics(repository, "7D")
    assert len(analytics["period_comparison"]) == 3
    assert all(item["total_tokens"] == item["events"] == 0 for item in analytics["period_comparison"])
    assert all(item["activity_tokens"] == item["activity_events"] == 0 for item in analytics["period_comparison"])
