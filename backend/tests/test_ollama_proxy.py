"""Ollama 代理数值提取回归测试。"""

from app.services.ollama_proxy import OllamaProxy, _UsageCapture


def test_stream_capture_reads_only_final_usage_chunk() -> None:
    capture = _UsageCapture()
    first_delta = capture.feed(
        b'{"response":"hello","done":false}\n{"model":"qwen-test",'
    )
    final_delta = capture.feed(
        b'"done":true,"prompt_eval_count":12,"eval_count":8,'
        b'"eval_duration":400000000}\n'
    )
    capture.finish()

    event = OllamaProxy._build_event(
        capture.metrics,
        request_id="req-stream",
        endpoint="/api/generate",
        requested_model="fallback",
    )

    assert event is not None
    assert event.model == "qwen-test"
    assert event.prompt_tokens == 12
    assert event.completion_tokens == 8
    assert event.tokens_per_second == 20
    assert first_delta == 1
    assert final_delta == 0


def test_stream_capture_counts_chat_and_openai_compatible_fragments() -> None:
    """原生 chat 与 OpenAI 兼容流都应驱动实时估算。"""

    capture = _UsageCapture()
    delta = capture.feed(
        b'{"message":{"content":"A"},"done":false}\n'
        b'{"choices":[{"delta":{"content":"B"}}]}\n'
    )

    assert delta == 2
