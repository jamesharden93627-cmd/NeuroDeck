"""并行聚合采集器并维护实时 Overview 状态。"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timezone

from app.collectors.antigravity import AntigravityCollector
from app.collectors.codex import CodexCollector
from app.collectors.hardware import HardwareCollector
from app.collectors.ollama import OllamaCollector
from app.db.history import HistoryRange, HistoryRepository
from app.schemas.dashboard import (
    HardwareSnapshot,
    OverviewSnapshot,
    ProviderSnapshot,
    SignalEvent,
    TrendPoint,
)


class DashboardService:
    """隔离采集器故障，并生成前端使用的单一事实快照。"""

    def __init__(
        self,
        ollama: OllamaCollector,
        codex: CodexCollector,
        hardware: HardwareCollector,
        antigravity: AntigravityCollector | None = None,
        history_repository: HistoryRepository | None = None,
        history_sample_interval_seconds: float = 10.0,
    ) -> None:
        self._ollama = ollama
        self._codex = codex
        self._hardware = hardware
        self._antigravity = antigravity
        self._history_repository = history_repository
        self._history_sample_interval_seconds = max(
            1.0,
            history_sample_interval_seconds,
        )
        self._last_history_sample_at = 0.0
        self._history: deque[TrendPoint] = deque(maxlen=720)
        self._signals: deque[SignalEvent] = deque(maxlen=40)
        self._latest: OverviewSnapshot | None = None
        self._storage_healthy = True
        self._collector_healthy = True

    async def health(self) -> dict[str, object]:
        """分别检查采集新鲜度、采集异常和存储连通性，而非固定返回 Healthy。"""

        age = (datetime.now(timezone.utc) - self._latest.timestamp).total_seconds() if self._latest else None
        collector = "unknown" if age is None else "stale" if age > 15 else "healthy" if self._collector_healthy else "degraded"
        storage_ok = self._storage_healthy
        if self._history_repository:
            storage_ok = storage_ok and await asyncio.to_thread(self._history_repository.check_health)
        storage = "healthy" if storage_ok else "degraded"
        return {"status": "ok" if collector == storage == "healthy" else "degraded",
                "api": "healthy", "collector": collector, "storage": storage,
                "snapshot_age_seconds": round(age, 1) if age is not None else None}

    def codex_accounting(self, days: int = 30) -> dict[str, int]:
        """公开数值对账结果，便于解释重复通知过滤后的用量变化。"""

        return self._codex.usage_audit(days)

    def antigravity_accounting(self, days: int = 30) -> dict[str, int]:
        """公开 Antigravity 数值对账结果。"""

        if self._antigravity is None:
            return {}
        return self._antigravity.usage_audit(days)

    @property
    def latest(self) -> OverviewSnapshot | None:
        """返回最近一次完成的快照。"""

        return self._latest

    async def initialize(self) -> None:
        """初始化本地数据库，并恢复最近趋势和事件流。"""

        if self._history_repository is None:
            return
        await asyncio.to_thread(self._history_repository.initialize)
        history, signals = await asyncio.gather(
            asyncio.to_thread(self._history_repository.query_history, "24H"),
            asyncio.to_thread(self._history_repository.load_recent_signals, 40),
        )
        self._history.extend(history)
        self._signals.extend(signals)

    async def get_history(self, time_range: HistoryRange) -> list[TrendPoint]:
        """返回持久化聚合历史；未配置数据库时回退到进程内趋势。"""

        if self._history_repository is None:
            return list(self._history)
        return await asyncio.to_thread(
            self._history_repository.query_history, time_range
        )

    async def close(self) -> None:
        """释放持久客户端资源。"""

        await self._ollama.close()

    async def collect(self) -> OverviewSnapshot:
        """并行执行采集器，避免慢数据源形成瀑布等待。"""

        coros: list[Any] = [
            self._ollama.collect(),
            self._codex.collect(),
            self._hardware.collect(),
        ]
        if self._antigravity is not None:
            coros.append(self._antigravity.collect())

        results = await asyncio.gather(*coros, return_exceptions=True)
        ollama = self._provider_or_offline("ollama", results[0])
        codex = self._provider_or_offline("codex", results[1])
        hardware = (
            results[2]
            if isinstance(results[2], HardwareSnapshot)
            else HardwareSnapshot()
        )
        if self._antigravity is not None and len(results) > 3:
            antigravity = self._provider_or_offline("antigravity", results[3])
        else:
            antigravity = ProviderSnapshot(provider="antigravity", online=False, status="offline")
        self._collector_healthy = not any(isinstance(result, Exception) for result in results)

        previous = self._latest
        new_signals = self._record_signals(previous, ollama, codex, hardware, antigravity)
        point = TrendPoint(
            ollama_tokens=ollama.total_tokens,
            codex_tokens=codex.total_tokens,
            antigravity_tokens=antigravity.total_tokens,
            ollama_tokens_per_second=ollama.tokens_per_second,
            cpu_usage=hardware.cpu_usage,
            gpu_usage=hardware.gpu_usage,
            gpu_temperature_c=hardware.gpu_temperature_c,
            ram_usage=self._percent(hardware.ram_used_gb, hardware.ram_total_gb),
            vram_usage=self._percent(hardware.vram_used_gb, hardware.vram_total_gb),
        )
        self._history.append(point)

        # 处理：实时内存态保持 1 秒，SQLite 默认 10 秒采样；状态事件仍立即持久化。
        if self._history_repository is not None:
            now = time.monotonic()
            should_save_sample = (
                now - self._last_history_sample_at
                >= self._history_sample_interval_seconds
            )
            if should_save_sample or new_signals:
                try:
                    if should_save_sample:
                        await asyncio.to_thread(
                            self._history_repository.save_sample,
                            point,
                            new_signals,
                        )
                        self._last_history_sample_at = now
                    else:
                        await asyncio.to_thread(
                            self._history_repository.save_signals,
                            new_signals,
                        )
                except Exception as exc:  # noqa: BLE001 - 数据库错误需要隔离并呈现在信号流。
                    if self._storage_healthy:
                        self._push_signal(
                            "STORAGE",
                            "WRITE ERROR",
                            type(exc).__name__,
                            "error",
                        )
                    self._storage_healthy = False
                else:
                    if not self._storage_healthy:
                        self._push_signal(
                            "STORAGE",
                            "WRITE RESTORED",
                            "SQLite online",
                        )
                    self._storage_healthy = True

        self._latest = OverviewSnapshot(
            timestamp=datetime.now(timezone.utc),
            ollama=ollama,
            codex=codex,
            antigravity=antigravity,
            # 对账与同一轮快照共享内存状态，避免活跃生成时跨请求比较产生瞬时误差。
            codex_accounting={
                "24H": self._codex.usage_audit(1),
                "7D": self._codex.usage_audit(7),
                "30D": self._codex.usage_audit(30),
            },
            antigravity_accounting={
                "24H": self._antigravity.usage_audit(1),
                "7D": self._antigravity.usage_audit(7),
                "30D": self._antigravity.usage_audit(30),
            } if self._antigravity is not None else {},
            hardware=hardware,
            history=list(self._history),
            recent_signals=self._recent_signal_view(),
        )
        return self._latest

    def _recent_signal_view(self, limit: int = 12) -> list[SignalEvent]:
        """折叠连续同源同类事件，避免高频 Token 更新淹没连接与告警状态。"""

        visible: list[SignalEvent] = []
        previous_key: tuple[str, str] | None = None
        for signal in self._signals:
            key = (signal.source, signal.event)
            if key == previous_key:
                continue
            visible.append(signal)
            previous_key = key
            if len(visible) >= limit:
                break
        return visible

    @staticmethod
    def _provider_or_offline(
        provider: str, result: object
    ) -> ProviderSnapshot:
        if isinstance(result, ProviderSnapshot):
            return result
        return ProviderSnapshot(
            provider=provider,
            online=False,
            status="error",
            detail=f"Collector error: {type(result).__name__}",
        )

    def _record_signals(
        self,
        previous: OverviewSnapshot | None,
        ollama: ProviderSnapshot,
        codex: ProviderSnapshot,
        hardware: HardwareSnapshot,
        antigravity: ProviderSnapshot | None = None,
    ) -> list[SignalEvent]:
        """只记录状态变化和阈值事件，避免每秒产生无意义噪音。"""

        created: list[SignalEvent] = []

        if previous is None:
            created.extend(
                [
                    self._push_signal(
                        "SYSTEM", "COLLECTORS READY", "Local telemetry active"
                    ),
                    self._push_signal(
                        "OLLAMA",
                        "CONNECTED" if ollama.online else "OFFLINE",
                        ollama.model,
                        "ok" if ollama.online else "warn",
                    ),
                    self._push_signal(
                        "CODEX",
                        "CONNECTED" if codex.online else "OFFLINE",
                        codex.model,
                        "ok" if codex.online else "warn",
                    ),
                ]
            )
            if antigravity is not None and antigravity.online:
                created.append(
                    self._push_signal(
                        "ANTIGRAVITY",
                        "CONNECTED",
                        antigravity.model,
                        "ok",
                    )
                )
            return created

        if previous.ollama.online != ollama.online:
            created.append(
                self._push_signal(
                    "OLLAMA",
                    "CONNECTED" if ollama.online else "DISCONNECTED",
                    ollama.model,
                    "ok" if ollama.online else "warn",
                )
            )
        if previous.ollama.model != ollama.model:
            created.append(self._push_signal("OLLAMA", "MODEL CHANGED", ollama.model))
        # 处理：请求完成后用校准后的精确累计值生成事件，排除上一帧在途估算造成的误差。
        if ollama.completed_requests_today > previous.ollama.completed_requests_today:
            previous_exact_output = max(
                0,
                previous.ollama.output_tokens - previous.ollama.live_output_tokens,
            )
            completion_delta = max(0, ollama.output_tokens - previous_exact_output)
            created.append(
                self._push_signal(
                    "OLLAMA",
                    "INFERENCE COMPLETE",
                    f"+{completion_delta:,} tokens · {ollama.last_tokens_per_second:.1f} t/s",
                )
            )
        if codex.total_tokens > previous.codex.total_tokens:
            delta = codex.total_tokens - previous.codex.total_tokens
            created.append(
                self._push_signal("CODEX", "TOKEN UPDATE", f"+{delta:,} tokens")
            )
        elif codex.total_tokens < previous.codex.total_tokens:
            # 边界：本地午夜后每日计数归零属于正常换日，不应伪装成 +0 token。
            created.append(
                self._push_signal("CODEX", "DAILY COUNTER RESET", "Local day boundary")
            )
        if antigravity is not None and hasattr(previous, "antigravity"):
            if previous.antigravity.online != antigravity.online:
                created.append(
                    self._push_signal(
                        "ANTIGRAVITY",
                        "CONNECTED" if antigravity.online else "DISCONNECTED",
                        antigravity.model,
                        "ok" if antigravity.online else "warn",
                    )
                )
            if previous.antigravity.model != antigravity.model:
                created.append(
                    self._push_signal("ANTIGRAVITY", "MODEL CHANGED", antigravity.model)
                )
            if antigravity.total_tokens > previous.antigravity.total_tokens:
                delta = antigravity.total_tokens - previous.antigravity.total_tokens
                created.append(
                    self._push_signal("ANTIGRAVITY", "TOKEN UPDATE", f"+{delta:,} tokens")
                )
            elif antigravity.total_tokens < previous.antigravity.total_tokens:
                created.append(
                    self._push_signal("ANTIGRAVITY", "DAILY COUNTER RESET", "Local day boundary")
                )
        if hardware.gpu_available and hardware.gpu_usage >= 90 > previous.hardware.gpu_usage:
            created.append(
                self._push_signal(
                    "GPU", "HIGH UTILIZATION", f"{hardware.gpu_usage:.0f}%", "warn"
                )
            )
        return created

    def _push_signal(
        self, source: str, event: str, detail: str, severity: str = "ok"
    ) -> SignalEvent:
        signal = SignalEvent(
            source=source,
            event=event,
            detail=detail,
            severity=severity,
        )
        self._signals.appendleft(signal)
        return signal

    @staticmethod
    def _percent(used: float, total: float) -> float:
        return round(used / total * 100, 1) if total else 0.0
