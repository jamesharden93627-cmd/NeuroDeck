"""Ollama 在途推理的内存态指标。"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(frozen=True, slots=True)
class OllamaLiveSnapshot:
    """提供给采集器的聚合快照；所有 token 数都属于流式估算。"""

    model: str = ""
    inflight_requests: int = 0
    estimated_output_tokens: int = 0
    estimated_tokens_per_second: float = 0.0


@dataclass(slots=True)
class _InflightRequest:
    """单个代理请求的最小匿名状态，不保存提示词或响应正文。"""

    model: str
    started_at: float
    estimated_output_tokens: int = 0


class OllamaLiveTracker:
    """聚合正在生成的请求，用于在官方最终统计到达前驱动实时 UI。"""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._requests: dict[str, _InflightRequest] = {}

    def start(self, request_id: str, model: str) -> None:
        """登记一个在途请求；只记录模型名和计时信息。"""

        self._requests[request_id] = _InflightRequest(
            model=model,
            started_at=self._clock(),
        )

    def progress(self, request_id: str, token_delta: int) -> None:
        """合并流式输出片段估算；未知或非正增量会被忽略。"""

        request = self._requests.get(request_id)
        if request is None or token_delta <= 0:
            return
        request.estimated_output_tokens += token_delta

    def finish(self, request_id: str) -> None:
        """结束在途状态，随后由 SQLite 中的官方统计接管展示。"""

        self._requests.pop(request_id, None)

    def snapshot(self) -> OllamaLiveSnapshot:
        """返回所有在途请求的实时聚合，不暴露任何生成正文。"""

        if not self._requests:
            return OllamaLiveSnapshot()

        now = self._clock()
        token_total = sum(
            request.estimated_output_tokens for request in self._requests.values()
        )
        elapsed_total = sum(
            max(now - request.started_at, 0.001)
            for request in self._requests.values()
        )
        # 说明：并发请求采用总输出 / 总生成时长，避免把不同起点的瞬时速度相加。
        estimated_speed = token_total / elapsed_total if token_total else 0.0
        latest = max(self._requests.values(), key=lambda request: request.started_at)
        return OllamaLiveSnapshot(
            model=latest.model,
            inflight_requests=len(self._requests),
            estimated_output_tokens=token_total,
            estimated_tokens_per_second=round(estimated_speed, 2),
        )
