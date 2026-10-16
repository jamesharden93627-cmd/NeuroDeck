"""Ollama 被动状态采集器。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.collectors.base import BaseCollector
from app.db.history import HistoryRepository
from app.schemas.dashboard import OllamaUsageSummary, ProviderSnapshot
from app.services.ollama_live import OllamaLiveSnapshot, OllamaLiveTracker


class OllamaCollector(BaseCollector[ProviderSnapshot]):
    """通过 Ollama 官方 API 获取加载模型与上下文信息。

    已完成请求使用 SQLite 中的 Ollama 官方计数；在途请求使用明确标记的流式估算。
    """

    def __init__(
        self,
        base_url: str,
        history_repository: HistoryRepository | None = None,
        live_tracker: OllamaLiveTracker | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=2.5)
        self._history_repository = history_repository
        self._live_tracker = live_tracker

    async def close(self) -> None:
        """关闭复用的 HTTP 连接池。"""

        await self._client.aclose()

    async def collect(self) -> ProviderSnapshot:
        """采集当前加载模型；Ollama 不可达时返回明确的离线快照。"""

        usage_task = asyncio.create_task(self._load_usage_summary())
        live = self._load_live_snapshot()
        try:
            response = await self._client.get("/api/ps")
            response.raise_for_status()
            models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError) as exc:
            usage = await usage_task
            return self._snapshot(
                usage,
                live,
                provider="ollama",
                online=False,
                status="offline",
                model=usage.model or "Unavailable",
                detail=f"Ollama unavailable: {type(exc).__name__}",
            )

        usage = await usage_task
        if not models:
            return self._snapshot(
                usage,
                live,
                provider="ollama",
                online=True,
                status="active" if live.inflight_requests else "idle",
                model=live.model or usage.model or "No model loaded",
                detail=(
                    "LIVE ESTIMATE · exact metrics on completion"
                    if live.inflight_requests
                    else "Ollama online · last proxy request"
                    if usage.last_request_at
                    else "Ollama online · proxy waiting"
                ),
            )

        active = models[0]
        model_name = str(active.get("name") or active.get("model") or "Unknown model")
        model_capacity, quantization = await self._load_model_details(model_name)
        # 口径：/api/ps 的 context_length 是当前加载实例的运行时限制；
        # /api/show 仅作为旧版 Ollama 缺少该字段时的模型容量回退。
        runtime_context = active.get("context_length")
        context_size = (
            int(runtime_context)
            if isinstance(runtime_context, (int, float)) and runtime_context > 0
            else model_capacity
        )
        size_gb = float(active.get("size_vram") or active.get("size") or 0) / 1024**3

        return self._snapshot(
            usage,
            live,
            provider="ollama",
            online=True,
            status="active" if live.inflight_requests else "idle",
            model=live.model or model_name,
            context_size=context_size,
            detail=(
                ("LIVE ESTIMATE · " if live.inflight_requests else "")
                + f"{size_gb:.1f} GB loaded"
                + (f" · {quantization}" if quantization else "")
                + (f" · {usage.requests_today} proxy req" if usage.requests_today else "")
            ),
        )

    def _snapshot(
        self,
        usage: OllamaUsageSummary,
        live: OllamaLiveSnapshot,
        **values: Any,
    ) -> ProviderSnapshot:
        """合并精确历史和在途估算；空闲吞吐归零，最近精确速度单独保留。"""

        is_live = live.inflight_requests > 0
        live_tokens = live.estimated_output_tokens
        return ProviderSnapshot(
            total_tokens=usage.total_tokens + live_tokens,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens + live_tokens,
            tokens_per_second=(
                live.estimated_tokens_per_second
                if is_live
                else 0.0
            ),
            last_tokens_per_second=usage.tokens_per_second,
            context_used=usage.context_used,
            sessions_today=usage.requests_today,
            completed_requests_today=usage.completed_requests_today,
            previous_day_tokens=usage.previous_day_tokens,
            # 处理：在途输出同时计入所有包含今天的范围，完成后由精确记录校准。
            tokens_7d=usage.tokens_7d + live_tokens,
            tokens_30d=usage.tokens_30d + live_tokens,
            range_usage={
                key: breakdown.model_copy(update={
                    "total_tokens": breakdown.total_tokens + live_tokens,
                    "output_tokens": breakdown.output_tokens + live_tokens,
                })
                for key, breakdown in usage.range_usage.items()
            },
            live_output_tokens=live_tokens,
            inflight_requests=live.inflight_requests,
            metric_precision="estimated" if is_live else "exact",
            **values,
        )

    def _load_live_snapshot(self) -> OllamaLiveSnapshot:
        """读取同进程代理的在途状态；未启用代理时保持精确历史模式。"""

        return self._live_tracker.snapshot() if self._live_tracker else OllamaLiveSnapshot()

    async def _load_usage_summary(self) -> OllamaUsageSummary:
        """从 SQLite 合并代理统计；数据库未启用时返回空汇总。"""

        if self._history_repository is None:
            return OllamaUsageSummary()
        return await asyncio.to_thread(
            self._history_repository.get_ollama_usage_summary
        )

    async def _load_model_details(self, model_name: str) -> tuple[int, str | None]:
        """读取模型上下文和量化信息；失败不会影响主状态。"""

        try:
            response = await self._client.post("/api/show", json={"model": model_name})
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError):
            return 0, None

        model_info = payload.get("model_info") or {}
        context_size = next(
            (
                int(value)
                for key, value in model_info.items()
                if str(key).endswith(".context_length")
                and isinstance(value, (int, float))
            ),
            0,
        )
        details = payload.get("details") or {}
        quantization = details.get("quantization_level")
        return context_size, str(quantization) if quantization else None
