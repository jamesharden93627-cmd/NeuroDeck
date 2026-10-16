"""独立 Ollama 代理入口回归测试。"""

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.services.ollama_proxy_listener import create_proxy_app


class _ProxyStub:
    """只记录转发目标，避免测试访问本机 Ollama。"""

    def __init__(self) -> None:
        self.path = ""
        self.query = ""

    async def forward(self, request: Request, path: str) -> JSONResponse:
        self.path = path
        self.query = request.url.query
        return JSONResponse({"forwarded": True})


def test_proxy_listener_keeps_native_ollama_path_and_query() -> None:
    """客户端切换端口后，路径和查询参数必须保持 Ollama 原生格式。"""

    proxy = _ProxyStub()
    app = create_proxy_app(proxy, "http://127.0.0.1:11434")  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.post("/api/chat?trace=1", json={"model": "qwen-test"})

    assert response.status_code == 200
    assert response.json() == {"forwarded": True}
    assert proxy.path == "api/chat"
    assert proxy.query == "trace=1"


def test_proxy_listener_health_does_not_touch_upstream() -> None:
    """本地健康检查应直接返回配置的真实 Ollama 地址。"""

    proxy = _ProxyStub()
    app = create_proxy_app(proxy, "http://127.0.0.1:11434")  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.get("/_neurodeck/health")

    assert response.json() == {
        "status": "ok",
        "upstream_url": "http://127.0.0.1:11434",
    }
    assert proxy.path == ""
