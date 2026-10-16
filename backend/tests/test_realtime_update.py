"""WebSocket 轻量增量协议回归测试。"""

from app.schemas.dashboard import (
    HardwareSnapshot,
    OverviewSnapshot,
    ProviderSnapshot,
    RealtimeUpdate,
    TrendPoint,
)


def test_realtime_update_only_contains_latest_history_point() -> None:
    """完整历史只通过 REST 发送，WebSocket 每帧只能携带最后一个趋势点。"""

    history = [TrendPoint(ollama_tokens=index) for index in range(720)]
    snapshot = OverviewSnapshot(
        ollama=ProviderSnapshot(provider="ollama"),
        codex=ProviderSnapshot(provider="codex"),
        hardware=HardwareSnapshot(),
        history=history,
    )

    update = RealtimeUpdate.from_snapshot(snapshot)

    assert update.history_point == history[-1]
    assert update.history == []
    assert len(update.model_dump_json()) < len(snapshot.model_dump_json()) / 10


def test_realtime_update_forwards_codex_accounting() -> None:
    """前端实时增长时对账与 Token 快照必须在同一帧更新。"""

    snapshot = OverviewSnapshot(
        ollama=ProviderSnapshot(provider="ollama"),
        codex=ProviderSnapshot(provider="codex", total_tokens=90),
        hardware=HardwareSnapshot(),
        codex_accounting={"24H": {"raw_tokens": 100, "accepted_tokens": 90,
                                    "duplicate_tokens": 10, "duplicate_events": 1}},
    )
    update = RealtimeUpdate.from_snapshot(snapshot)
    assert update.codex_accounting["24H"].accepted_tokens == update.codex.total_tokens
