"""NeuroDeck FastAPI 入口。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from ipaddress import ip_address
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

from app.collectors.antigravity import AntigravityCollector
from app.collectors.codex import CodexCollector
from app.collectors.hardware import HardwareCollector
from app.collectors.ollama import OllamaCollector
from app.core.config import settings
from app.db.antigravity_analytics import query_antigravity_analytics
from app.db.codex_analytics import query_codex_analytics
from app.db.history import HistoryRange, HistoryRepository
from app.db.operations import operations_csv, query_operations
from app.schemas.dashboard import (
    OverviewSnapshot,
    RealtimeUpdate,
    TokenActivityPoint,
    TokenVolumeBucket,
    TrendPoint,
)
from app.services.dashboard import DashboardService
from app.services.ollama_live import OllamaLiveTracker
from app.services.ollama_proxy import OllamaProxy
from app.services.ollama_proxy_listener import OllamaProxyListener


history_repository = HistoryRepository(
    settings.database_path, settings.history_retention_days
)
ollama_live_tracker = OllamaLiveTracker()
dashboard_service = DashboardService(
    ollama=OllamaCollector(
        settings.ollama_base_url,
        history_repository,
        ollama_live_tracker,
    ),
    codex=CodexCollector(
        settings.codex_home,
        settings.codex_tail_bytes,
        history_repository=history_repository,
    ),
    hardware=HardwareCollector(),
    antigravity=AntigravityCollector(
        settings.antigravity_home,
        settings.antigravity_tail_bytes,
        history_repository=history_repository,
    ),
    history_repository=history_repository,
    history_sample_interval_seconds=settings.history_sample_interval_seconds,
)
ollama_proxy = OllamaProxy(
    settings.ollama_base_url,
    history_repository,
    ollama_live_tracker,
)
ollama_proxy_listener = OllamaProxyListener(
    ollama_proxy,
    settings.ollama_base_url,
    settings.ollama_proxy_host,
    settings.ollama_proxy_port,
)
connected_clients: set[WebSocket] = set()
logger = logging.getLogger("neurodeck")

# 安全：浏览器实时连接只接受正式页面和本地 Vite 开发页的精确来源。
LOCAL_UI_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    f"http://127.0.0.1:{settings.port}",
    f"http://localhost:{settings.port}",
}


def _websocket_origin_allowed(origin: str | None, client_host: str | None) -> bool:
    """验证 WebSocket 来源；无 Origin 的原生客户端仅允许从回环地址连接。"""

    if origin is not None:
        return origin.rstrip("/") in LOCAL_UI_ORIGINS
    if not client_host:
        return False
    if client_host.lower() == "localhost":
        return True
    try:
        return ip_address(client_host).is_loopback
    except ValueError:
        return False


async def _broadcast(snapshot: OverviewSnapshot) -> None:
    """向浏览器推送轻量增量帧，失败连接会被安全移除。"""

    payload = RealtimeUpdate.from_snapshot(snapshot).model_dump_json()
    stale: list[WebSocket] = []
    for client in tuple(connected_clients):
        try:
            await client.send_text(payload)
        except (RuntimeError, WebSocketDisconnect):
            stale.append(client)
    for client in stale:
        connected_clients.discard(client)


async def _collection_loop() -> None:
    """持续采集；单次失败不会终止后台任务。"""

    while True:
        try:
            snapshot = await dashboard_service.collect()
            await _broadcast(snapshot)
        except Exception:  # noqa: BLE001 - 后台监控必须保持存活，但必须留下可诊断日志。
            logger.exception("后台采集或 WebSocket 广播失败")
        await asyncio.sleep(settings.collection_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动采集循环和 11435 Ollama 兼容代理，并统一释放资源。"""

    task: asyncio.Task[None] | None = None
    try:
        await dashboard_service.initialize()
        await dashboard_service.collect()
        await ollama_proxy_listener.start()
        task = asyncio.create_task(_collection_loop())
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await ollama_proxy_listener.close()
        await asyncio.gather(dashboard_service.close(), ollama_proxy.close())


app = FastAPI(
    title="NeuroDeck",
    version="0.2.0",
    description="Local AI observability and command center",
    lifespan=lifespan,
)

# 安全：开发环境只允许本机 Vite 和正式服务来源访问。
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(LOCAL_UI_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, object]:
    """返回轻量健康检查。"""

    return await dashboard_service.health()


@app.get("/api/codex/accounting")
async def codex_accounting(
    time_range: HistoryRange = Query(default="30D", alias="range"),
) -> dict[str, int]:
    """返回所选自然日范围的原始事件与去重后用量。"""

    return dashboard_service.codex_accounting({"24H": 1, "7D": 7, "30D": 30}[time_range])


@app.get("/api/antigravity/accounting")
async def antigravity_accounting(
    time_range: HistoryRange = Query(default="30D", alias="range"),
) -> dict[str, int]:
    """返回所选自然日范围的 Antigravity 原始事件与去重后用量。"""

    return dashboard_service.antigravity_accounting({"24H": 1, "7D": 7, "30D": 30}[time_range])


@app.get("/api/ollama/requests")
async def ollama_requests(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, object]]:
    """读取匿名请求结果，包括失败、取消和缺少精确用量的响应。"""

    return await asyncio.to_thread(history_repository.query_ollama_requests, limit)


@app.get("/api/dashboard/overview", response_model=OverviewSnapshot)
async def overview() -> OverviewSnapshot:
    """返回不含重复历史的状态快照；趋势由专用分桶接口加载。"""

    snapshot = dashboard_service.latest or await dashboard_service.collect()
    return snapshot.model_copy(update={"history": []})


@app.get("/api/analytics/history", response_model=list[TrendPoint])
async def analytics_history(
    time_range: HistoryRange = Query(default="24H", alias="range"),
) -> list[TrendPoint]:
    """返回 SQLite 中按显示范围分桶后的匿名化趋势指标。"""

    return await dashboard_service.get_history(time_range)


@app.get("/api/analytics/token-volume", response_model=list[TokenVolumeBucket])
async def token_volume(
    time_range: HistoryRange = Query(default="24H", alias="range"),
) -> list[TokenVolumeBucket]:
    """返回来自两个独立事件账本的真实 Token 增量柱状序列。"""

    return await asyncio.to_thread(history_repository.query_token_volume, time_range)


@app.get("/api/analytics/token-activity", response_model=list[TokenActivityPoint])
async def token_activity(
    time_range: HistoryRange = Query(default="24H", alias="range"),
) -> list[TokenActivityPoint]:
    """返回事件账本重建的范围累计 Token 曲线。"""

    return await asyncio.to_thread(history_repository.query_token_activity, time_range)


@app.get("/api/analytics/codex", response_model=None)
async def codex_analytics(
    time_range: HistoryRange = Query(default="24H", alias="range"),
) -> dict[str, object]:
    """返回匿名 Codex 账本的模型、工作区、会话和自然日分析。"""

    return await asyncio.to_thread(query_codex_analytics, history_repository, time_range)


@app.get("/api/analytics/antigravity", response_model=None)
async def antigravity_analytics(
    time_range: HistoryRange = Query(default="24H", alias="range"),
) -> dict[str, object]:
    """返回匿名 Antigravity 账本的模型、工作区、会话和自然日分析。"""

    return await asyncio.to_thread(query_antigravity_analytics, history_repository, time_range)


@app.get("/api/analytics/operations", response_model=None)
async def operations(
    time_range: HistoryRange = Query(default="24H", alias="range"),
    model: str = Query(default="", max_length=256),
    status: Literal["", "completed", "failed", "cancelled", "unmetered", "incomplete"] = "",
    search: str = Query(default="", max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    snapshot_id: int | None = Query(default=None, ge=0),
    format: Literal["json", "csv"] = "json",
) -> dict[str, object] | Response:
    """请求运营看板：按相同筛选返回统计、模型排行、逐日用量和记录。"""

    data = await asyncio.to_thread(query_operations, history_repository, time_range,
                                  model, status, search.strip(), page, page_size, snapshot_id)
    # 兼容：使用标准附件响应，避免部分嵌入式浏览器不能下载 Blob URL。
    if format == "csv":
        return Response(operations_csv(data["requests"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="neurodeck-ollama-{time_range}-page-{data["page"]}.csv"'})
    return data


@app.get("/api/ollama/proxy-status")
async def ollama_proxy_status() -> dict[str, object]:
    """返回代理接入地址与匿名累计状态，供详情页诊断连接。"""

    summary = await asyncio.to_thread(history_repository.get_ollama_usage_summary)
    live = ollama_live_tracker.snapshot()
    return {
        "proxy_url": ollama_proxy_listener.address,
        "upstream_url": settings.ollama_base_url,
        "requests_today": summary.requests_today,
        "total_tokens": summary.total_tokens,
        "tokens_7d": summary.tokens_7d,
        "tokens_30d": summary.tokens_30d,
        "last_request_at": summary.last_request_at,
        "inflight_requests": live.inflight_requests,
        "live_output_tokens": live.estimated_output_tokens,
        "metric_precision": "estimated" if live.inflight_requests else "exact",
    }


@app.api_route(
    "/ollama/{path:path}",
    methods=["GET", "POST", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_ollama(request: Request, path: str):
    """兼容旧版 5188 路径；新客户端应直接使用独立的 11435 端口。"""

    return await ollama_proxy.forward(request, path)


@app.websocket("/ws/realtime")
async def realtime(websocket: WebSocket) -> None:
    """推送实时快照，浏览器断开不会影响采集循环。"""

    client_host = websocket.client.host if websocket.client else None
    if not _websocket_origin_allowed(websocket.headers.get("origin"), client_host):
        await websocket.close(code=1008, reason="Local NeuroDeck origin required")
        return
    await websocket.accept()
    connected_clients.add(websocket)
    if dashboard_service.latest:
        await websocket.send_text(
            RealtimeUpdate.from_snapshot(dashboard_service.latest).model_dump_json()
        )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(websocket)


# 交付：存在 React production build 时由 FastAPI 同端口托管，开发时仍可使用 Vite。
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
