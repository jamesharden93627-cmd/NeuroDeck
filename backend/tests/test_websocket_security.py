"""本地 WebSocket 来源校验回归测试。"""

from app.main import _websocket_origin_allowed


def test_websocket_accepts_neurodeck_and_vite_origins() -> None:
    """正式页面、开发页和本机原生客户端可以连接实时通道。"""

    assert _websocket_origin_allowed("http://127.0.0.1:5188", "127.0.0.1")
    assert _websocket_origin_allowed("http://localhost:5173", "127.0.0.1")
    assert _websocket_origin_allowed(None, "::1")


def test_websocket_rejects_external_or_untrusted_local_origins() -> None:
    """外部网页与未登记的本地网页不能读取 NeuroDeck 实时遥测。"""

    assert not _websocket_origin_allowed("https://malicious.example", "127.0.0.1")
    assert not _websocket_origin_allowed("http://localhost:9999", "127.0.0.1")
    assert not _websocket_origin_allowed(None, "192.168.1.20")
    assert not _websocket_origin_allowed("null", "127.0.0.1")
