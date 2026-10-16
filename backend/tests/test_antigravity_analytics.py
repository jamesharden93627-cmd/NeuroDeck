"""Antigravity 匿名账本多维分析回归测试。"""

from datetime import datetime, timezone

from app.db.antigravity_analytics import query_antigravity_analytics
from app.db.history import HistoryRepository
from app.schemas.dashboard import AntigravityUsageEvent


def test_antigravity_analytics_groups_models_workspaces_and_sessions(tmp_path) -> None:
    """三个排行维度必须共享同一批事件，总量与缓存比例能够互相核对。"""

    repository = HistoryRepository(tmp_path / "antigravity-analytics.db")
    repository.initialize()
    now = datetime.now(timezone.utc)
    repository.save_antigravity_usage([
        AntigravityUsageEvent(
            timestamp=now,
            event_id="ag-one",
            session_id="session-alpha",
            model="Gemini 3.8",
            workspace_label="NeuroDeck",
            input_tokens=1000,
            output_tokens=200,
            cached_tokens=300,
            total_tokens=1500,
        ),
        AntigravityUsageEvent(
            timestamp=now,
            event_id="ag-two",
            session_id="session-beta",
            model="Claude Sonnet 4.6 (Thinking)",
            workspace_label="ClientApp",
            input_tokens=2000,
            output_tokens=500,
            cached_tokens=500,
            total_tokens=3000,
        ),
    ])

    analytics = query_antigravity_analytics(repository, "24H")

    assert analytics["summary"]["total_tokens"] == 4500
    assert analytics["summary"]["sessions"] == 2
    assert analytics["summary"]["workspaces"] == 2
    assert analytics["summary"]["models"] == 2
    assert analytics["models"][0]["model"] == "Claude Sonnet 4.6 (Thinking)"
    assert analytics["models"][0]["total_tokens"] == 3000
    assert analytics["workspaces"][0]["workspace"] == "ClientApp"
    assert analytics["workspaces"][0]["total_tokens"] == 3000
    assert analytics["sessions"][0]["session"] == "AG-SESSION-"
    assert analytics["daily"][-1]["total_tokens"] == 4500
