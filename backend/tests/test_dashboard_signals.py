"""Dashboard 跨帧事件生成回归测试。"""

from collections import deque

from app.schemas.dashboard import HardwareSnapshot, OverviewSnapshot, ProviderSnapshot
from app.services.dashboard import DashboardService


def test_ollama_completion_signal_excludes_previous_live_estimate() -> None:
    """最终输出增量应以完成前的精确基线计算，不能把在途估算重复计入。"""

    service = DashboardService.__new__(DashboardService)
    service._signals = deque(maxlen=40)
    previous = OverviewSnapshot(
        ollama=ProviderSnapshot(
            provider="ollama",
            sessions_today=2,
            completed_requests_today=2,
            output_tokens=756,
            live_output_tokens=452,
            inflight_requests=1,
            metric_precision="estimated",
        ),
        codex=ProviderSnapshot(provider="codex"),
        hardware=HardwareSnapshot(),
    )
    completed = ProviderSnapshot(
        provider="ollama",
        sessions_today=3,
        completed_requests_today=3,
        output_tokens=804,
        tokens_per_second=0,
        last_tokens_per_second=24.7,
    )

    created = service._record_signals(
        previous,
        completed,
        previous.codex,
        previous.hardware,
    )

    assert len(created) == 1
    assert created[0].source == "OLLAMA"
    assert created[0].event == "INFERENCE COMPLETE"
    assert created[0].detail == "+500 tokens · 24.7 t/s"


def test_recent_signal_view_collapses_only_consecutive_duplicates() -> None:
    """连续 Token 更新只展示最新一条，穿插告警后仍保留新的活动信号。"""

    service = DashboardService.__new__(DashboardService)
    service._signals = deque(maxlen=40)
    service._push_signal("CODEX", "TOKEN UPDATE", "+100 tokens")
    service._push_signal("GPU", "HIGH UTILIZATION", "95%", "warn")
    service._push_signal("CODEX", "TOKEN UPDATE", "+200 tokens")
    service._push_signal("CODEX", "TOKEN UPDATE", "+300 tokens")

    visible = service._recent_signal_view()

    assert [(item.source, item.detail) for item in visible] == [
        ("CODEX", "+300 tokens"),
        ("GPU", "95%"),
        ("CODEX", "+100 tokens"),
    ]
