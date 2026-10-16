"""Ollama 流式估算聚合器回归测试。"""

from app.services.ollama_live import OllamaLiveTracker


def test_live_tracker_aggregates_inflight_requests_without_content() -> None:
    """多个请求应汇总 token，并在结束后完整清理内存态。"""

    now = [100.0]
    tracker = OllamaLiveTracker(clock=lambda: now[0])
    tracker.start("req-a", "qwen-a")
    now[0] = 102.0
    tracker.progress("req-a", 20)
    tracker.start("req-b", "qwen-b")
    now[0] = 104.0
    tracker.progress("req-b", 10)

    live = tracker.snapshot()
    assert live.model == "qwen-b"
    assert live.inflight_requests == 2
    assert live.estimated_output_tokens == 30
    assert live.estimated_tokens_per_second == 5

    tracker.finish("req-a")
    tracker.finish("req-b")
    assert tracker.snapshot().inflight_requests == 0
