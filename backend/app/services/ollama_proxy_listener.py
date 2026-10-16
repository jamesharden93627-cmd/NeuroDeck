"""独立 Ollama 兼容代理监听器。"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import contextmanager, suppress

import uvicorn
from fastapi import FastAPI, Request

from app.services.ollama_proxy import OllamaProxy


class _EmbeddedServer(uvicorn.Server):
    """嵌入主服务运行的 Uvicorn Server，由 5188 主服务统一处理系统信号。"""

    @contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        """避免 11435 子服务覆盖主 Uvicorn 的退出信号处理器。"""

        yield


def create_proxy_app(proxy: OllamaProxy, upstream_url: str) -> FastAPI:
    """创建只暴露 Ollama 协议的轻量 ASGI 应用。"""

    proxy_app = FastAPI(
        title="NeuroDeck Ollama Proxy",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @proxy_app.get("/_neurodeck/health")
    async def proxy_health() -> dict[str, str]:
        """供启动脚本检查代理端口，不向上游制造探测请求。"""

        return {"status": "ok", "upstream_url": upstream_url}

    @proxy_app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def forward_ollama(request: Request, path: str):
        """保持原始 Ollama 路径，让客户端仅需替换 Base URL。"""

        return await proxy.forward(request, path)

    return proxy_app


class OllamaProxyListener:
    """在主进程内监听独立端口，并与仪表盘共享实时追踪状态。"""

    def __init__(
        self,
        proxy: OllamaProxy,
        upstream_url: str,
        host: str,
        port: int,
    ) -> None:
        proxy_app = create_proxy_app(proxy, upstream_url)
        config = uvicorn.Config(
            proxy_app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
        self._server = _EmbeddedServer(config)
        self._task: asyncio.Task[None] | None = None
        self._address = f"http://{host}:{port}"

    @property
    def address(self) -> str:
        """返回客户端应配置的 Ollama Base URL。"""

        return self._address

    async def start(self) -> None:
        """启动代理并等待端口完成绑定；端口冲突会阻止假成功。"""

        self._task = asyncio.create_task(
            self._server.serve(),
            name="neurodeck-ollama-proxy",
        )
        for _ in range(100):
            if self._server.started:
                return
            if self._task.done():
                await self._task
                raise RuntimeError(f"Ollama proxy failed to bind {self._address}")
            await asyncio.sleep(0.05)

        self._server.should_exit = True
        raise TimeoutError(f"Ollama proxy startup timed out: {self._address}")

    async def close(self) -> None:
        """通知子服务优雅退出，并回收后台任务。"""

        if self._task is None:
            return
        self._server.should_exit = True
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
