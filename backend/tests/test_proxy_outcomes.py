"""代理兼容响应与失败/取消记录测试；全部使用模拟上游，不调用真实模型。"""

import asyncio
import json
import sqlite3

import httpx
from starlette.requests import Request

from app.db.history import HistoryRepository
from app.schemas.dashboard import OllamaUsageEvent
from app.services.ollama_live import OllamaLiveTracker
from app.services.ollama_proxy import OllamaProxy, _UsageCapture


def test_sse_fragmentation_and_usage() -> None:
    capture = _UsageCapture()
    raw = (b': keepalive\n\ndata: {"choices":[{"delta":{"content":"A"}}]}\n\n'
           b'data: {"model":"test","usage":{"prompt_tokens":12,"completion_tokens":8}}\n\n'
           b'data: [DONE]\n\n')
    fragments = sum(capture.feed(raw[i:i + 7]) for i in range(0, len(raw), 7))
    assert fragments == 1
    capture.finish()
    event = OllamaProxy._build_event(capture.metrics, request_id="test", endpoint="/v1/chat/completions", requested_model="test")
    assert event.prompt_tokens == 12
    assert event.completion_tokens == 8
    assert capture.done


def test_nonstream_usage_and_sse_multiline() -> None:
    for raw in (b'{"usage":{"prompt_tokens":2,"completion_tokens":3}}',
                b'data: {"usage":\ndata: {"prompt_tokens":2,"completion_tokens":3}}\n\n'):
        capture = _UsageCapture()
        capture.feed(raw)
        capture.finish()
        assert capture.metrics["eval_count"] == 3


def test_malformed_usage_is_unavailable_instead_of_throwing() -> None:
    for value in ("unknown", -1, float("inf"), True):
        assert OllamaProxy._build_event({"eval_count": value}, request_id="bad", endpoint="/api/chat", requested_model="test") is None


def make_request(path="/api/chat") -> Request:
    """生成匿名测试请求，不复用用户请求或提示词。"""

    async def receive():
        return {"type": "http.request", "body": b'{"model":"test"}', "more_body": False}
    return Request({"type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
                    "path": path, "query_string": b"", "headers": [], "server": ("test", 80)}, receive)


class Stream(httpx.AsyncByteStream):
    def __init__(self, body: bytes):
        self.body = body

    async def __aiter__(self):
        yield self.body


def test_failed_unmetered_and_native_requests_recorded(tmp_path) -> None:
    async def run():
        repository = HistoryRepository(tmp_path / "outcomes.db")
        repository.initialize()
        tracker = OllamaLiveTracker()
        proxy = OllamaProxy("http://test", repository, tracker)
        await proxy._client.aclose()
        responses = iter([
            (500, b'{"error":"private upstream detail"}'),
            (200, b'{"done":true}\n'),
            (200, b'{"done":true,"prompt_eval_count":2,"eval_count":3}\n'),
        ])
        def handler(request):
            code, body = next(responses)
            return httpx.Response(code, stream=Stream(body))
        proxy._client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
        for _ in range(3):
            response = await proxy.forward(make_request(), "api/chat")
            async for _ in response.body_iterator:
                pass
            assert tracker.snapshot().inflight_requests == 0
        await proxy.close()
        rows = repository.query_ollama_requests()
        assert {row["status"] for row in rows} == {"completed", "unmetered", "failed"}
        assert "private upstream detail" not in json.dumps(rows)
        assert repository.get_ollama_usage_summary().total_tokens == 5
    asyncio.run(run())


def test_connection_failure_is_recorded_and_sanitized(tmp_path) -> None:
    async def run():
        repository = HistoryRepository(tmp_path / "connection.db")
        repository.initialize()
        tracker = OllamaLiveTracker()
        proxy = OllamaProxy("http://test", repository, tracker)
        await proxy._client.aclose()
        def handler(request):
            raise httpx.ConnectError("private diagnostic")
        proxy._client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
        response = await proxy.forward(make_request(), "api/chat")
        assert response.status_code == 502
        await proxy.close()
        assert tracker.snapshot().inflight_requests == 0
        row = repository.query_ollama_requests()[0]
        assert row["status"] == "failed"
        assert row["metric_precision"] == "unavailable"
    asyncio.run(run())


def test_v1_migration_preserves_usage_and_backup(tmp_path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.execute('''CREATE TABLE ollama_usage_events (
            id INTEGER PRIMARY KEY, timestamp TEXT, request_id TEXT UNIQUE, endpoint TEXT, model TEXT,
            prompt_tokens INTEGER, completion_tokens INTEGER, total_duration_ns INTEGER,
            prompt_eval_duration_ns INTEGER, eval_duration_ns INTEGER, tokens_per_second REAL)''')
        event = OllamaUsageEvent(request_id="old", endpoint="/api/chat", model="test", prompt_tokens=10)
        connection.execute("INSERT INTO ollama_usage_events VALUES (1, ?, 'old', '/api/chat', 'test', 10, 0, 0, 0, 0, 0)",
                           (HistoryRepository._serialize_time(event.timestamp),))
    repository = HistoryRepository(path)
    repository.initialize()
    repository.initialize()
    assert repository.get_ollama_usage_summary().total_tokens == 10
    assert path.with_suffix(".pre-v2.db").exists()


def test_stream_cancelled_records_unknown_usage_and_cleans_inflight(tmp_path) -> None:
    async def run():
        repository = HistoryRepository(tmp_path / "cancelled.db")
        repository.initialize()
        tracker = OllamaLiveTracker()
        proxy = OllamaProxy("http://test", repository, tracker)
        await proxy._client.aclose()
        proxy._client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Stream(b'{"response":"A"}\n'))))
        response = await proxy.forward(make_request(), "api/chat")
        iterator = response.body_iterator
        await anext(iterator)
        assert tracker.snapshot().inflight_requests == 1
        await iterator.aclose()
        await proxy.close()
        assert tracker.snapshot().inflight_requests == 0
        row = repository.query_ollama_requests()[0]
        assert row["status"] == "cancelled"
        assert row["metric_precision"] == "unavailable"
        summary = repository.get_ollama_usage_summary()
        assert summary.requests_today == 1
        assert summary.completed_requests_today == 0
    asyncio.run(run())


def test_cancel_before_headers_also_records_request(tmp_path) -> None:
    async def run():
        repository = HistoryRepository(tmp_path / "cancel-before.db")
        repository.initialize()
        tracker = OllamaLiveTracker()
        proxy = OllamaProxy("http://test", repository, tracker)
        await proxy._client.aclose()
        def handler(request):
            raise asyncio.CancelledError()
        proxy._client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
        try:
            await proxy.forward(make_request(), "api/chat")
        except asyncio.CancelledError:
            pass
        await proxy.close()
        assert tracker.snapshot().inflight_requests == 0
        assert repository.query_ollama_requests()[0]["status"] == "cancelled"
    asyncio.run(run())
