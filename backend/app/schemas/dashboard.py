"""Overview API 使用的统一数据结构。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from app.core.time_ranges import calendar_range_starts


def utc_now() -> datetime:
    """返回带时区的 UTC 时间，避免前端混用本地时间与无时区时间。"""

    return datetime.now(timezone.utc)


class UsageBreakdown(BaseModel):
    """单个供应商在一个时间范围内的精确用量分项。"""

    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    interactions: int = 0
    exact_completions: int = 0


class ProviderSnapshot(BaseModel):
    """Ollama 或 Codex 的标准化实时状态。"""

    provider: str
    online: bool = False
    model: str = "Unavailable"
    status: str = "offline"
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    tokens_per_second: float = 0.0
    last_tokens_per_second: float = 0.0
    context_used: int = 0
    context_size: int = 0
    sessions_today: int = 0
    completed_requests_today: int = 0
    previous_day_tokens: int = 0
    tokens_7d: int = 0
    tokens_30d: int = 0
    range_usage: dict[str, UsageBreakdown] = Field(default_factory=dict)
    live_output_tokens: int = 0
    inflight_requests: int = 0
    metric_precision: str = "exact"
    detail: str | None = None


class HardwareSnapshot(BaseModel):
    """本机 CPU、内存与首张 GPU 的实时状态。"""

    cpu_usage: float = 0.0
    cpu_frequency_mhz: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    gpu_available: bool = False
    gpu_name: str = "GPU unavailable"
    gpu_usage: float = 0.0
    vram_used_gb: float = 0.0
    vram_total_gb: float = 0.0
    gpu_temperature_c: float | None = None
    gpu_power_w: float | None = None
    gpu_fan_percent: float | None = None
    uptime_seconds: int = 0


class TrendPoint(BaseModel):
    """硬件和实时吞吐量的采样趋势；Token 长周期曲线使用独立事件账本。"""

    timestamp: datetime = Field(default_factory=utc_now)
    ollama_tokens: int = 0
    codex_tokens: int = 0
    antigravity_tokens: int = 0
    ollama_tokens_per_second: float = 0.0
    cpu_usage: float = 0.0
    gpu_usage: float = 0.0
    gpu_temperature_c: float | None = None
    ram_usage: float = 0.0
    vram_usage: float = 0.0


class SignalEvent(BaseModel):
    """Overview 右下角最近信号流中的一条安全事件。"""

    timestamp: datetime = Field(default_factory=utc_now)
    source: str
    event: str
    detail: str
    severity: str = "ok"


class OllamaUsageEvent(BaseModel):
    """一次经过 NeuroDeck 代理的匿名化 Ollama 使用记录。"""

    timestamp: datetime = Field(default_factory=utc_now)
    request_id: str
    endpoint: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_duration_ns: int = 0
    prompt_eval_duration_ns: int = 0
    eval_duration_ns: int = 0
    tokens_per_second: float = 0.0
    status: str = "completed"
    http_status: int | None = None
    metric_precision: str = "exact"
    error_type: str | None = None


class CodexUsageEvent(BaseModel):
    """一次从 Codex 本地日志提取的匿名 Token 用量事件。

    total_tokens 是本次响应增量；activity_tokens 保留同一时刻的会话累计快照，
    仅用于与 Codex 桌面端“Token 活动”这类累计样本口径对账。
    """

    timestamp: datetime = Field(default_factory=utc_now)
    event_id: str
    session_id: str
    model: str = ""
    workspace_id: str = ""
    workspace_label: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    activity_tokens: int = 0


class AntigravityUsageEvent(BaseModel):
    """一次从 Antigravity transcript 提取的匿名 Token 用量事件。"""

    timestamp: datetime = Field(default_factory=utc_now)
    event_id: str
    session_id: str
    model: str = ""
    workspace_label: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0


class TokenVolumeBucket(BaseModel):
    """按小时或自然日聚合的供应商 Token 增量。"""

    timestamp: datetime
    ollama_tokens: int = 0
    codex_tokens: int = 0
    antigravity_tokens: int = 0


class TokenActivityPoint(BaseModel):
    """从事件账本按固定时间桶重建的供应商累计 Token 曲线点。"""

    timestamp: datetime
    ollama_tokens: int = 0
    codex_tokens: int = 0
    antigravity_tokens: int = 0


class CodexUsageSummary(BaseModel):
    """Codex 持久化事件在常用自然日范围内的汇总。"""

    model: str = ""
    previous_day_tokens: int = 0
    range_usage: dict[str, UsageBreakdown] = Field(default_factory=dict)


class AntigravityUsageSummary(BaseModel):
    """Antigravity 持久化事件在常用自然日范围内的汇总。"""

    model: str = ""
    previous_day_tokens: int = 0
    range_usage: dict[str, UsageBreakdown] = Field(default_factory=dict)


class OllamaUsageSummary(BaseModel):
    """Ollama Collector 合并使用的代理累计统计。"""

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tokens_per_second: float = 0.0
    context_used: int = 0
    requests_today: int = 0
    completed_requests_today: int = 0
    previous_day_tokens: int = 0
    tokens_7d: int = 0
    tokens_30d: int = 0
    range_usage: dict[str, UsageBreakdown] = Field(default_factory=dict)
    last_request_at: datetime | None = None


class AccountingSummary(BaseModel):
    """Codex 本地日志在一个自然日范围内的原始值与去重结果。"""

    raw_tokens: int = 0
    accepted_tokens: int = 0
    duplicate_tokens: int = 0
    duplicate_events: int = 0


class OverviewSnapshot(BaseModel):
    """前端首次加载与 WebSocket 推送共用的完整快照。"""

    timestamp: datetime = Field(default_factory=utc_now)
    mode: str = "live"
    range_starts: dict[str, datetime] = Field(default_factory=calendar_range_starts)
    ollama: ProviderSnapshot
    codex: ProviderSnapshot
    antigravity: ProviderSnapshot = Field(
        default_factory=lambda: ProviderSnapshot(provider="antigravity", online=False, status="offline")
    )
    codex_accounting: dict[str, AccountingSummary] = Field(default_factory=dict)
    antigravity_accounting: dict[str, AccountingSummary] = Field(default_factory=dict)
    hardware: HardwareSnapshot
    history: list[TrendPoint] = Field(default_factory=list)
    recent_signals: list[SignalEvent] = Field(default_factory=list)


class RealtimeUpdate(BaseModel):
    """WebSocket 使用的轻量增量帧，避免每秒重复发送整段历史。"""

    type: Literal["realtime_update"] = "realtime_update"
    timestamp: datetime = Field(default_factory=utc_now)
    mode: str = "live"
    range_starts: dict[str, datetime] = Field(default_factory=calendar_range_starts)
    ollama: ProviderSnapshot
    codex: ProviderSnapshot
    antigravity: ProviderSnapshot = Field(
        default_factory=lambda: ProviderSnapshot(provider="antigravity", online=False, status="offline")
    )
    codex_accounting: dict[str, AccountingSummary] = Field(default_factory=dict)
    antigravity_accounting: dict[str, AccountingSummary] = Field(default_factory=dict)
    hardware: HardwareSnapshot
    history_point: TrendPoint | None = None
    # 兼容：旧版前端会读取 history.at(-1)；保留空数组可避免热升级时页面崩溃。
    history: list[TrendPoint] = Field(default_factory=list)
    recent_signals: list[SignalEvent] = Field(default_factory=list)

    @classmethod
    def from_snapshot(cls, snapshot: OverviewSnapshot) -> "RealtimeUpdate":
        """从完整 REST 快照生成单点增量，保留实时页面所需状态。"""

        return cls(
            timestamp=snapshot.timestamp,
            mode=snapshot.mode,
            range_starts=snapshot.range_starts,
            ollama=snapshot.ollama,
            codex=snapshot.codex,
            antigravity=snapshot.antigravity,
            codex_accounting=snapshot.codex_accounting,
            antigravity_accounting=snapshot.antigravity_accounting,
            hardware=snapshot.hardware,
            history_point=snapshot.history[-1] if snapshot.history else None,
            recent_signals=snapshot.recent_signals,
        )
