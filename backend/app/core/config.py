"""应用配置。所有默认值均限制在本机，避免意外暴露监控数据。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """NeuroDeck 运行配置。

    配置只从环境变量读取；用户没有显式设置时，服务仅监听 localhost。
    """

    host: str = os.getenv("NEURODECK_HOST", "127.0.0.1")
    port: int = int(os.getenv("NEURODECK_PORT", "5188"))
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_proxy_host: str = os.getenv("OLLAMA_PROXY_HOST", "127.0.0.1")
    ollama_proxy_port: int = int(os.getenv("OLLAMA_PROXY_PORT", "11435"))
    codex_home: Path = Path(
        os.getenv("CODEX_HOME", str(Path.home() / ".codex"))
    ).expanduser()
    collection_interval_seconds: float = float(
        # 体验：1 秒刷新可以看清流式 token 变化，同时避免按模型 token 频率重采硬件。
        os.getenv("NEURODECK_COLLECTION_INTERVAL", "1")
    )
    history_sample_interval_seconds: float = max(
        1.0,
        float(os.getenv("NEURODECK_HISTORY_SAMPLE_INTERVAL", "10")),
    )
    codex_tail_bytes: int = int(os.getenv("NEURODECK_CODEX_TAIL_BYTES", "2097152"))
    antigravity_home: Path = Path(
        os.getenv("ANTIGRAVITY_HOME", str(Path.home() / ".gemini" / "antigravity"))
    ).expanduser()
    antigravity_tail_bytes: int = int(os.getenv("NEURODECK_ANTIGRAVITY_TAIL_BYTES", "2097152"))
    database_path: Path = Path(
        os.getenv(
            "NEURODECK_DATABASE_PATH",
            str(Path(__file__).resolve().parents[3] / "data" / "neurodeck.db"),
        )
    ).expanduser()
    history_retention_days: int = int(
        os.getenv("NEURODECK_HISTORY_RETENTION_DAYS", "30")
    )


settings = Settings()
