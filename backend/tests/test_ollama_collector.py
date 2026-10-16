"""Ollama 状态、上下文与吞吐口径回归测试。"""

import asyncio

import httpx

from app.collectors.ollama import OllamaCollector
from app.schemas.dashboard import OllamaUsageSummary
from app.services.ollama_live import OllamaLiveSnapshot


def test_idle_snapshot_resets_live_speed_but_keeps_last_exact_speed() -> None:
    """生成结束后当前速度必须归零，最近一次精确速度仍供完成事件使用。"""

    collector = OllamaCollector("http://unused")
    snapshot = collector._snapshot(
        OllamaUsageSummary(
            total_tokens=120,
            tokens_7d=450,
            tokens_30d=900,
            tokens_per_second=24.5,
            context_used=4_096,
        ),
        OllamaLiveSnapshot(),
        provider="ollama",
        online=True,
        status="idle",
    )
    asyncio.run(collector.close())

    assert snapshot.tokens_per_second == 0
    assert snapshot.last_tokens_per_second == 24.5
    assert snapshot.context_used == 4_096
    assert snapshot.total_tokens == 120
    assert snapshot.tokens_7d == 450
    assert snapshot.tokens_30d == 900


def test_loaded_runtime_context_takes_priority_over_model_capacity() -> None:
    """页面应显示 /api/ps 的 32K 运行时配置，而不是模型文件声明的 256K 上限。"""

    async def collect() -> tuple[int, str]:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/ps":
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {
                                "name": "qwen-test",
                                "context_length": 32_768,
                                "size_vram": 1024,
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "model_info": {"qwen.context_length": 262_144},
                    "details": {"quantization_level": "Q4"},
                },
            )

        collector = OllamaCollector("http://test")
        await collector._client.aclose()
        collector._client = httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.MockTransport(handler),
        )
        try:
            snapshot = await collector.collect()
            return snapshot.context_size, snapshot.status
        finally:
            await collector.close()

    context_size, status = asyncio.run(collect())
    assert context_size == 32_768
    assert status == "idle"
