"""Ollama 隐私安全流式代理。"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.db.history import HistoryRepository
from app.schemas.dashboard import OllamaUsageEvent
from app.services.ollama_live import OllamaLiveTracker


_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class _UsageCapture:
    """提取最终官方指标，并按流式输出片段估算在途 token。"""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.metrics: dict[str, Any] | None = None
        self._sse_data: list[bytes] = []
        self.done = False
        self.failed = False

    def feed(self, chunk: bytes) -> int:
        """消费原始响应并返回新出现的输出片段数，正文不会被持久化。"""

        estimated_delta = 0
        self._buffer.extend(chunk)
        while b"\n" in self._buffer:
            raw_line, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            estimated_delta += self._consume_line(raw_line)
        return estimated_delta

    def finish(self) -> int:
        """处理非换行结尾的最后一个 JSON 块。"""

        estimated_delta = 0
        if self._buffer:
            estimated_delta = self._consume_line(bytes(self._buffer))
        self._buffer.clear()
        estimated_delta += self._flush_sse()
        return estimated_delta

    def _consume_line(self, raw: bytes) -> int:
        """兼容原生 NDJSON 和 SSE 帧；事件名前缀、注释与终止帧不属于 JSON。"""

        raw = raw.rstrip(b"\r")
        if raw.startswith(b"data:"):
            self._sse_data.append(raw[5:].lstrip(b" "))
            return 0
        if not raw:
            return self._flush_sse()
        if raw.startswith((b":", b"event:", b"id:", b"retry:")):
            return 0
        return self._inspect(raw)

    def _flush_sse(self) -> int:
        """按 SSE 的空行边界合并 data 行，支持跨网络包分割。"""

        if not self._sse_data:
            return 0
        raw = b"\n".join(self._sse_data)
        self._sse_data.clear()
        return self._inspect(raw)

    def _inspect(self, raw: bytes) -> int:
        if not raw.strip():
            return 0
        if raw.strip() == b"[DONE]":
            self.done = True
            return 0
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return 0
        if not isinstance(payload, dict):
            return 0
        self.failed = self.failed or bool(payload.get("error"))
        choices = payload.get("choices")
        self.done = self.done or payload.get("done") is True or (
            isinstance(choices, list) and any(isinstance(item, dict) and item.get("finish_reason") is not None for item in choices)
        )
        if "prompt_eval_count" in payload or "eval_count" in payload:
            self.metrics = payload
            return 0
        # 口径：OpenAI 兼容响应的 usage 可以提供精确 token，但没有 Ollama 原生生成耗时。
        usage = payload.get("usage")
        if isinstance(usage, dict) and ("prompt_tokens" in usage or "completion_tokens" in usage):
            self.metrics = {
                "model": payload.get("model"),
                "prompt_eval_count": usage.get("prompt_tokens", 0),
                "eval_count": usage.get("completion_tokens", 0),
            }
            self.done = True
        return self._count_output_fragments(payload)

    @staticmethod
    def _count_output_fragments(payload: dict[str, Any]) -> int:
        """识别 generate/chat/OpenAI 兼容流中的非空输出片段。

        Ollama 通常按模型 token 输出一个片段，但协议没有保证一一对应，
        因此该数值只用于带明确标记的实时估算，最终必须以 eval_count 校准。
        """

        fragments: list[Any] = [payload.get("response"), payload.get("thinking")]
        message = payload.get("message")
        if isinstance(message, dict):
            fragments.extend([message.get("content"), message.get("thinking")])
        choices = payload.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    fragments.extend([delta.get("content"), delta.get("reasoning")])
        return sum(1 for fragment in fragments if isinstance(fragment, str) and fragment)


class OllamaProxy:
    """原样转发 Ollama 请求，并在最终响应块中提取匿名使用指标。"""

    def __init__(
        self,
        upstream_base_url: str,
        repository: HistoryRepository,
        live_tracker: OllamaLiveTracker,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=upstream_base_url, timeout=httpx.Timeout(None, connect=10, write=60, pool=10))
        self._repository = repository
        self._live_tracker = live_tracker
        self._pending_records: set[asyncio.Task[None]] = set()

    async def close(self) -> None:
        """关闭代理复用的上游连接池。"""

        await self._client.aclose()
        if self._pending_records:
            await asyncio.gather(*tuple(self._pending_records), return_exceptions=True)

    def _record(self, event: OllamaUsageEvent) -> None:
        """独立落盘任务不随客户端断线取消；只记录错误类型，禁止日志包含请求正文。"""

        async def save() -> None:
            try:
                await asyncio.to_thread(self._repository.save_ollama_usage, event)
            except Exception as exc:
                logging.getLogger("neurodeck").error("代理记录写入失败: %s", type(exc).__name__)
        task = asyncio.create_task(save())
        self._pending_records.add(task)
        task.add_done_callback(self._pending_records.discard)

    async def forward(self, request: Request, path: str) -> StreamingResponse | JSONResponse:
        """转发任意 Ollama API 路径，流式响应不会被缓冲后再返回。"""

        request_body = await request.body()
        requested_model = self._read_model(request_body)
        upstream_path = f"/{path}"
        if request.url.query:
            upstream_path = f"{upstream_path}?{request.url.query}"

        upstream_request = self._client.build_request(
            request.method,
            upstream_path,
            headers=self._forward_headers(request.headers),
            content=request_body,
        )
        request_id = uuid4().hex
        tracked = request.method == "POST" and path.strip("/") in {
            "api/chat", "api/generate", "v1/chat/completions", "v1/completions",
        }
        # 实时性：上游首字节可能要等待模型加载或 prompt eval，必须在等待前登记请求。
        if tracked:
            self._live_tracker.start(request_id, requested_model)
        try:
            upstream_response = await self._client.send(upstream_request, stream=True)
        except (Exception, asyncio.CancelledError) as exc:
            self._live_tracker.finish(request_id)
            if tracked:
                self._record(OllamaUsageEvent(
                    request_id=request_id, endpoint=f"/{path}", model=requested_model,
                    status="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
                    metric_precision="unavailable", error_type=type(exc).__name__,
                ))
            if isinstance(exc, httpx.HTTPError):
                return JSONResponse({"error": "Ollama upstream unavailable"}, status_code=502)
            raise
        response_headers = {
            key: value
            for key, value in upstream_response.headers.items()
            if key.lower() not in _HOP_BY_HOP_HEADERS
        }
        capture = _UsageCapture()

        async def stream_body() -> AsyncIterator[bytes]:
            outcome = "incomplete"
            error_type = None
            try:
                async for chunk in upstream_response.aiter_raw():
                    if tracked:
                        self._live_tracker.progress(request_id, capture.feed(chunk))
                    yield chunk
                outcome = "completed"
            except (asyncio.CancelledError, GeneratorExit):
                outcome = "cancelled"
                error_type = "ClientDisconnected"
                raise
            except Exception as exc:
                outcome = "failed"
                error_type = type(exc).__name__
                raise
            finally:
                if tracked:
                    capture.finish()
                    if upstream_response.status_code >= 400 or capture.failed:
                        outcome, error_type = "failed", "UpstreamError"
                    elif outcome == "completed" and capture.metrics is None:
                        outcome = "unmetered" if capture.done else "incomplete"
                    event = self._build_event(
                        capture.metrics, request_id=request_id,
                        endpoint=f"/{path}", requested_model=requested_model,
                    )
                    if event is None:
                        if outcome == "completed":
                            outcome, error_type = "incomplete", "InvalidUsage"
                        event = OllamaUsageEvent(
                            request_id=request_id, endpoint=f"/{path}", model=requested_model,
                            metric_precision="unavailable",
                        )
                    self._record(event.model_copy(update={
                        "status": outcome, "http_status": upstream_response.status_code,
                        "error_type": error_type,
                    }))
                # 处理：无论异常还是取消都清理在途状态，持久化任务不依赖客户端连接。
                self._live_tracker.finish(request_id)
                await upstream_response.aclose()

        return StreamingResponse(
            stream_body(),
            status_code=upstream_response.status_code,
            headers=response_headers,
        )

    @staticmethod
    def _forward_headers(headers: Any) -> dict[str, str]:
        """移除仅对当前连接有效的头，其他 Ollama 兼容头保持不变。"""

        return {
            key: value
            for key, value in headers.items()
            if key.lower() not in _HOP_BY_HOP_HEADERS | {"host", "content-length"}
        }

    @staticmethod
    def _read_model(request_body: bytes) -> str:
        """请求正文只在内存中读取模型名，不写入日志或数据库。"""

        try:
            payload = json.loads(request_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "Unknown model"
        if not isinstance(payload, dict):
            return "Unknown model"
        return str(payload.get("model") or "Unknown model")

    @staticmethod
    def _build_event(
        metrics: dict[str, Any] | None,
        *,
        request_id: str,
        endpoint: str,
        requested_model: str,
    ) -> OllamaUsageEvent | None:
        """把官方纳秒计时字段转换为可直接展示的 tokens/s。"""

        if metrics is None:
            return None
        # 兼容：异常上游不能使 finally 中的清理抛错；缺失数值按 0，畸形值标为不可用。
        for key in ("prompt_eval_count", "eval_count", "eval_duration", "total_duration", "prompt_eval_duration"):
            value = metrics.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                return None
        prompt_tokens = int(metrics.get("prompt_eval_count") or 0)
        completion_tokens = int(metrics.get("eval_count") or 0)
        eval_duration_ns = int(metrics.get("eval_duration") or 0)
        tokens_per_second = (
            completion_tokens / (eval_duration_ns / 1_000_000_000)
            if completion_tokens and eval_duration_ns
            else 0.0
        )
        return OllamaUsageEvent(
            request_id=request_id,
            endpoint=endpoint,
            model=str(metrics.get("model") or requested_model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_duration_ns=int(metrics.get("total_duration") or 0),
            prompt_eval_duration_ns=int(metrics.get("prompt_eval_duration") or 0),
            eval_duration_ns=eval_duration_ns,
            tokens_per_second=round(tokens_per_second, 2),
        )
