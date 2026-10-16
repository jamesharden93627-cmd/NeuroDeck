"""SQLite 历史指标仓库。"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from app.core.time_ranges import calendar_range_start

from app.schemas.dashboard import (
    AntigravityUsageEvent,
    AntigravityUsageSummary,
    CodexUsageEvent,
    CodexUsageSummary,
    OllamaUsageEvent,
    OllamaUsageSummary,
    SignalEvent,
    TokenActivityPoint,
    TokenVolumeBucket,
    TrendPoint,
    UsageBreakdown,
)


HistoryRange = Literal["24H", "7D", "30D"]

_RANGE_CONFIG: dict[HistoryRange, tuple[timedelta, int]] = {
    "24H": (timedelta(hours=24), 5 * 60),
    "7D": (timedelta(days=7), 30 * 60),
    "30D": (timedelta(days=30), 2 * 60 * 60),
}


class HistoryRepository:
    """保存匿名化趋势点与信号事件，并提供固定上限的时间分桶查询。

    数据库只包含数值指标和状态信息，不保存 prompt、response 或工具输出。
    每个操作使用独立连接，使后台写入和 API 查询可通过 WAL 安全并发。
    """

    def __init__(self, database_path: Path, retention_days: int = 30) -> None:
        self._database_path = database_path
        self._retention_days = max(1, retention_days)
        self._last_prune_at = 0.0

    @property
    def database_path(self) -> Path:
        """返回实际数据库路径，供健康状态与诊断页面展示。"""

        return self._database_path

    def initialize(self) -> None:
        """创建数据库目录、表和查询索引；重复调用不会破坏已有数据。"""

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trend_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ollama_tokens INTEGER NOT NULL,
                    codex_tokens INTEGER NOT NULL,
                    antigravity_tokens INTEGER NOT NULL DEFAULT 0,
                    ollama_tokens_per_second REAL NOT NULL,
                    cpu_usage REAL NOT NULL,
                    gpu_usage REAL NOT NULL,
                    gpu_temperature_c REAL,
                    ram_usage REAL NOT NULL,
                    vram_usage REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trend_points_timestamp
                    ON trend_points(timestamp);

                CREATE TABLE IF NOT EXISTS signal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    event TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    severity TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_signal_events_timestamp
                    ON signal_events(timestamp);

                CREATE TABLE IF NOT EXISTS ollama_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    endpoint TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_duration_ns INTEGER NOT NULL,
                    prompt_eval_duration_ns INTEGER NOT NULL,
                    eval_duration_ns INTEGER NOT NULL,
                    tokens_per_second REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    http_status INTEGER,
                    metric_precision TEXT NOT NULL DEFAULT 'exact',
                    error_type TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_ollama_usage_timestamp
                    ON ollama_usage_events(timestamp);

                CREATE TABLE IF NOT EXISTS codex_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    workspace_label TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cached_tokens INTEGER NOT NULL,
                    reasoning_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    activity_tokens INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_codex_usage_timestamp
                    ON codex_usage_events(timestamp);

                CREATE TABLE IF NOT EXISTS antigravity_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    workspace_label TEXT NOT NULL DEFAULT '',
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cached_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_antigravity_usage_timestamp
                    ON antigravity_usage_events(timestamp);
                """
            )
            self._migrate_usage(connection)
            self._migrate_trends(connection)
            self._migrate_codex_usage(connection)
            self._migrate_antigravity_usage(connection)

    def _migrate_usage(self, connection: sqlite3.Connection) -> None:
        """非破坏迁移：旧表仅补字段，首次升级前通过 SQLite 在线备份保留原库。"""

        columns = {row["name"] for row in connection.execute("PRAGMA table_info(ollama_usage_events)")}
        additions = {"status": "TEXT NOT NULL DEFAULT 'completed'", "http_status": "INTEGER",
                     "metric_precision": "TEXT NOT NULL DEFAULT 'exact'", "error_type": "TEXT"}
        missing = [(key, definition) for key, definition in additions.items() if key not in columns]
        backup_path = self._database_path.with_suffix(".pre-v2.db")
        if missing and not backup_path.exists():
            with sqlite3.connect(backup_path) as backup:
                connection.backup(backup)
        for key, definition in missing:
            connection.execute(f"ALTER TABLE ollama_usage_events ADD COLUMN {key} {definition}")
        connection.execute("PRAGMA user_version = 2")

    def _migrate_trends(self, connection: sqlite3.Connection) -> None:
        """非破坏补充真实温度历史列和 Antigravity token 列。"""

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(trend_points)")
        }
        if "gpu_temperature_c" not in columns:
            connection.execute(
                "ALTER TABLE trend_points ADD COLUMN gpu_temperature_c REAL"
            )
        if "antigravity_tokens" not in columns:
            connection.execute(
                "ALTER TABLE trend_points ADD COLUMN antigravity_tokens INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute("PRAGMA user_version = 4")

    def _migrate_codex_usage(self, connection: sqlite3.Connection) -> None:
        """非破坏补充匿名工作区与活动快照字段，并在升级前保留在线备份。"""

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(codex_usage_events)")
        }
        additions = {
            "workspace_id": "TEXT NOT NULL DEFAULT ''",
            "workspace_label": "TEXT NOT NULL DEFAULT ''",
            "activity_tokens": "INTEGER NOT NULL DEFAULT 0",
        }
        missing = [(key, definition) for key, definition in additions.items() if key not in columns]
        # 兼容：v5 库只缺活动快照列；更老的库也通过同一次 v6 迁移补齐全部字段。
        backup_path = self._database_path.with_suffix(".pre-v6.db")
        if missing and not backup_path.exists():
            with sqlite3.connect(backup_path) as backup:
                connection.backup(backup)
        for key, definition in missing:
            connection.execute(f"ALTER TABLE codex_usage_events ADD COLUMN {key} {definition}")
        connection.execute("PRAGMA user_version = 6")

    def _migrate_antigravity_usage(self, connection: sqlite3.Connection) -> None:
        """方案 A：确保历史 Antigravity 记录中的 total_tokens 包含完整的上下文缓存吞吐。"""
        connection.execute(
            """
            UPDATE antigravity_usage_events
            SET total_tokens = input_tokens + output_tokens + cached_tokens
            WHERE total_tokens = input_tokens + output_tokens AND cached_tokens > 0
            """
        )

    def check_health(self) -> bool:
        """只读验证指标表可访问；不创建缺失数据库，也不把连通性当作写入成功。"""

        try:
            with sqlite3.connect(f"file:{self._database_path.as_posix()}?mode=ro", uri=True, timeout=1) as connection:
                connection.execute("SELECT id FROM trend_points LIMIT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def save_sample(self, point: TrendPoint, signals: list[SignalEvent]) -> None:
        """原子保存一个趋势点及同轮产生的信号，并定期清理过期记录。"""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trend_points (
                    timestamp, ollama_tokens, codex_tokens, antigravity_tokens,
                    ollama_tokens_per_second, cpu_usage, gpu_usage,
                    gpu_temperature_c, ram_usage, vram_usage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._serialize_time(point.timestamp),
                    point.ollama_tokens,
                    point.codex_tokens,
                    point.antigravity_tokens,
                    point.ollama_tokens_per_second,
                    point.cpu_usage,
                    point.gpu_usage,
                    point.gpu_temperature_c,
                    point.ram_usage,
                    point.vram_usage,
                ),
            )
            connection.executemany(
                self._signal_insert_sql(),
                self._signal_rows(signals),
            )
            self._prune_if_due(connection)

    def save_signals(self, signals: list[SignalEvent]) -> None:
        """在趋势点尚未到落盘周期时，独立保存需要立即可见的状态事件。"""

        if not signals:
            return
        with self._connect() as connection:
            connection.executemany(
                self._signal_insert_sql(),
                self._signal_rows(signals),
            )

    def query_history(self, time_range: HistoryRange) -> list[TrendPoint]:
        """按范围返回约 288～360 个趋势点，避免长周期数据压垮前端。"""

        _, bucket_seconds = _RANGE_CONFIG[time_range]
        cutoff = self._serialize_time(calendar_range_start(time_range))
        end = self._serialize_time(datetime.now(timezone.utc))
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH ranked AS (
                    SELECT
                        *,
                        CAST(strftime('%s', timestamp) / ? AS INTEGER) AS bucket,
                        ROW_NUMBER() OVER (
                            PARTITION BY CAST(strftime('%s', timestamp) / ? AS INTEGER)
                            ORDER BY timestamp DESC, id DESC
                        ) AS row_number
                    FROM trend_points
                    WHERE timestamp >= ? AND timestamp <= ?
                )
                SELECT
                    MAX(CASE WHEN row_number = 1 THEN timestamp END) AS timestamp,
                    MAX(CASE WHEN row_number = 1 THEN ollama_tokens END) AS ollama_tokens,
                    MAX(CASE WHEN row_number = 1 THEN codex_tokens END) AS codex_tokens,
                    MAX(CASE WHEN row_number = 1 THEN antigravity_tokens END) AS antigravity_tokens,
                    AVG(ollama_tokens_per_second) AS ollama_tokens_per_second,
                    AVG(cpu_usage) AS cpu_usage,
                    AVG(gpu_usage) AS gpu_usage,
                    AVG(gpu_temperature_c) AS gpu_temperature_c,
                    AVG(ram_usage) AS ram_usage,
                    AVG(vram_usage) AS vram_usage
                FROM ranked
                GROUP BY bucket
                ORDER BY bucket ASC
                """,
                (bucket_seconds, bucket_seconds, cutoff, end),
            ).fetchall()

        return [
            TrendPoint(
                timestamp=row["timestamp"],
                ollama_tokens=row["ollama_tokens"],
                codex_tokens=row["codex_tokens"],
                antigravity_tokens=int(row["antigravity_tokens"] or 0),
                ollama_tokens_per_second=round(row["ollama_tokens_per_second"], 2),
                cpu_usage=round(row["cpu_usage"], 2),
                gpu_usage=round(row["gpu_usage"], 2),
                gpu_temperature_c=(
                    round(row["gpu_temperature_c"], 2)
                    if row["gpu_temperature_c"] is not None
                    else None
                ),
                ram_usage=round(row["ram_usage"], 2),
                vram_usage=round(row["vram_usage"], 2),
            )
            for row in rows
        ]

    def load_recent_signals(self, limit: int = 40) -> list[SignalEvent]:
        """在服务重启后恢复最近信号，保持事件面板连续。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, source, event, detail, severity
                FROM signal_events
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [SignalEvent(**dict(row)) for row in rows]

    def save_ollama_usage(self, event: OllamaUsageEvent) -> None:
        """保存代理响应的数值统计，明确排除请求和响应正文。"""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO ollama_usage_events (
                    timestamp, request_id, endpoint, model,
                    prompt_tokens, completion_tokens, total_duration_ns,
                    prompt_eval_duration_ns, eval_duration_ns, tokens_per_second,
                    status, http_status, metric_precision, error_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._serialize_time(event.timestamp),
                    event.request_id,
                    event.endpoint,
                    event.model,
                    event.prompt_tokens,
                    event.completion_tokens,
                    event.total_duration_ns,
                    event.prompt_eval_duration_ns,
                    event.eval_duration_ns,
                    event.tokens_per_second,
                    event.status,
                    event.http_status,
                    event.metric_precision,
                    event.error_type,
                ),
            )

    def save_codex_usage(self, events: list[CodexUsageEvent]) -> None:
        """批量写入 Codex 匿名事件；事件指纹保证重启和归档移动不会重复。"""

        if not events:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO codex_usage_events (
                    timestamp, event_id, session_id, model, workspace_id, workspace_label,
                    input_tokens, output_tokens, cached_tokens,
                    reasoning_tokens, total_tokens, activity_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    model = CASE WHEN excluded.model <> '' THEN excluded.model ELSE model END,
                    workspace_id = CASE WHEN excluded.workspace_id <> '' THEN excluded.workspace_id ELSE workspace_id END,
                    workspace_label = CASE WHEN excluded.workspace_label <> '' THEN excluded.workspace_label ELSE workspace_label END,
                    activity_tokens = CASE
                        WHEN excluded.activity_tokens > 0 THEN excluded.activity_tokens
                        ELSE activity_tokens
                    END
                """,
                [
                    (
                        self._serialize_time(event.timestamp),
                        event.event_id,
                        event.session_id,
                        event.model,
                        event.workspace_id,
                        event.workspace_label,
                        event.input_tokens,
                        event.output_tokens,
                        event.cached_tokens,
                        event.reasoning_tokens,
                        event.total_tokens,
                        event.activity_tokens,
                    )
                    for event in events
                ],
            )

    def get_codex_usage_summary(self) -> CodexUsageSummary:
        """从独立账本汇总 Codex 用量，使源日志移动或删除后总量仍可恢复。"""

        now = datetime.now(timezone.utc)
        ranges = {
            key: calendar_range_start(key, now)
            for key in ("24H", "7D", "30D")
        }
        local_today = now.astimezone().date()
        yesterday_start = datetime.combine(
            local_today - timedelta(days=1), datetime.min.time()
        ).astimezone(timezone.utc)
        today_start = ranges["24H"]
        end = self._serialize_time(now)

        with self._connect() as connection:
            usage: dict[str, UsageBreakdown] = {}
            for key, start in ranges.items():
                row = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                        COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                        COUNT(DISTINCT session_id) AS sessions,
                        COUNT(*) AS completions
                    FROM codex_usage_events
                    WHERE timestamp >= ? AND timestamp <= ?
                    """,
                    (self._serialize_time(start), end),
                ).fetchone()
                usage[key] = UsageBreakdown(
                    total_tokens=int(row["total_tokens"]),
                    input_tokens=int(row["input_tokens"]),
                    output_tokens=int(row["output_tokens"]),
                    cached_tokens=int(row["cached_tokens"]),
                    reasoning_tokens=int(row["reasoning_tokens"]),
                    interactions=int(row["sessions"]),
                    exact_completions=int(row["completions"]),
                )

            previous_day_tokens = connection.execute(
                """
                SELECT COALESCE(SUM(total_tokens), 0)
                FROM codex_usage_events
                WHERE timestamp >= ? AND timestamp < ?
                """,
                (
                    self._serialize_time(yesterday_start),
                    self._serialize_time(today_start),
                ),
            ).fetchone()[0]
            latest = connection.execute(
                """
                SELECT model FROM codex_usage_events
                WHERE timestamp <= ? AND model <> ''
                ORDER BY timestamp DESC, id DESC LIMIT 1
                """,
                (end,),
            ).fetchone()

        return CodexUsageSummary(
            model=str(latest["model"]) if latest else "",
            previous_day_tokens=int(previous_day_tokens),
            range_usage=usage,
        )

    def save_antigravity_usage(self, events: list[AntigravityUsageEvent]) -> None:
        """批量写入 Antigravity 匿名事件；事件指纹保证重启不会重复。"""

        if not events:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO antigravity_usage_events (
                    timestamp, event_id, session_id, model, workspace_label,
                    input_tokens, output_tokens, cached_tokens, total_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    model = CASE WHEN excluded.model <> '' THEN excluded.model ELSE model END,
                    workspace_label = CASE WHEN excluded.workspace_label <> '' THEN excluded.workspace_label ELSE workspace_label END,
                    total_tokens = excluded.total_tokens
                """,
                [
                    (
                        self._serialize_time(event.timestamp),
                        event.event_id,
                        event.session_id,
                        event.model,
                        event.workspace_label,
                        event.input_tokens,
                        event.output_tokens,
                        event.cached_tokens,
                        event.total_tokens,
                    )
                    for event in events
                ],
            )

    def get_antigravity_usage_summary(self) -> AntigravityUsageSummary:
        """从独立账本汇总 Antigravity 用量。"""

        now = datetime.now(timezone.utc)
        ranges = {
            key: calendar_range_start(key, now)
            for key in ("24H", "7D", "30D")
        }
        local_today = now.astimezone().date()
        yesterday_start = datetime.combine(
            local_today - timedelta(days=1), datetime.min.time()
        ).astimezone(timezone.utc)
        today_start = ranges["24H"]
        end = self._serialize_time(now)

        with self._connect() as connection:
            usage: dict[str, UsageBreakdown] = {}
            for key, start in ranges.items():
                row = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                        COUNT(DISTINCT session_id) AS sessions,
                        COUNT(*) AS completions
                    FROM antigravity_usage_events
                    WHERE timestamp >= ? AND timestamp <= ?
                    """,
                    (self._serialize_time(start), end),
                ).fetchone()
                usage[key] = UsageBreakdown(
                    total_tokens=int(row["total_tokens"]),
                    input_tokens=int(row["input_tokens"]),
                    output_tokens=int(row["output_tokens"]),
                    cached_tokens=int(row["cached_tokens"]),
                    reasoning_tokens=0,
                    interactions=int(row["sessions"]),
                    exact_completions=int(row["completions"]),
                )

            previous_day_tokens = connection.execute(
                """
                SELECT COALESCE(SUM(total_tokens), 0)
                FROM antigravity_usage_events
                WHERE timestamp >= ? AND timestamp < ?
                """,
                (
                    self._serialize_time(yesterday_start),
                    self._serialize_time(today_start),
                ),
            ).fetchone()[0]
            latest = connection.execute(
                """
                SELECT model FROM antigravity_usage_events
                WHERE timestamp <= ? AND model <> ''
                ORDER BY timestamp DESC, id DESC LIMIT 1
                """,
                (end,),
            ).fetchone()

        return AntigravityUsageSummary(
            model=str(latest["model"]) if latest else "",
            previous_day_tokens=int(previous_day_tokens),
            range_usage=usage,
        )

    def query_token_volume(self, time_range: HistoryRange) -> list[TokenVolumeBucket]:
        """按小时/自然日返回真实事件增量；补齐空桶，避免柱形图把缺数画成连续活动。"""

        now = datetime.now(timezone.utc)
        start = calendar_range_start(time_range, now)
        start_text = self._serialize_time(start)
        end_text = self._serialize_time(now)
        totals: dict[datetime, dict[str, int]] = {}

        with self._connect() as connection:
            codex_rows = connection.execute(
                """
                SELECT timestamp, total_tokens AS tokens
                FROM codex_usage_events
                WHERE timestamp >= ? AND timestamp <= ?
                """,
                (start_text, end_text),
            ).fetchall()
            ollama_rows = connection.execute(
                """
                SELECT timestamp, prompt_tokens + completion_tokens AS tokens
                FROM ollama_usage_events
                WHERE timestamp >= ? AND timestamp <= ?
                    AND status = 'completed' AND metric_precision = 'exact'
                """,
                (start_text, end_text),
            ).fetchall()
            antigravity_rows = connection.execute(
                """
                SELECT timestamp, total_tokens AS tokens
                FROM antigravity_usage_events
                WHERE timestamp >= ? AND timestamp <= ?
                """,
                (start_text, end_text),
            ).fetchall()

        # 处理：先转本机时区再截断，7D/30D 的柱子严格对应界面所说的自然日。
        def bucket_start(value: str) -> datetime:
            parsed = datetime.fromisoformat(value).astimezone()
            if time_range == "24H":
                return parsed.replace(minute=0, second=0, microsecond=0)
            return parsed.replace(hour=0, minute=0, second=0, microsecond=0)

        for provider, rows in (("codex", codex_rows), ("ollama", ollama_rows), ("antigravity", antigravity_rows)):
            for row in rows:
                bucket = bucket_start(row["timestamp"])
                values = totals.setdefault(bucket, {"ollama": 0, "codex": 0, "antigravity": 0})
                values[provider] += int(row["tokens"])

        cursor = start.astimezone()
        if time_range == "24H":
            cursor = cursor.replace(minute=0, second=0, microsecond=0)
            end_bucket = now.astimezone().replace(minute=0, second=0, microsecond=0)
            step = timedelta(hours=1)
        else:
            cursor = cursor.replace(hour=0, minute=0, second=0, microsecond=0)
            end_bucket = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
            step = timedelta(days=1)

        buckets: list[TokenVolumeBucket] = []
        while cursor <= end_bucket:
            values = totals.get(cursor, {"ollama": 0, "codex": 0, "antigravity": 0})
            buckets.append(
                TokenVolumeBucket(
                    timestamp=cursor.astimezone(timezone.utc),
                    ollama_tokens=values["ollama"],
                    codex_tokens=values["codex"],
                    antigravity_tokens=values["antigravity"],
                )
            )
            cursor += step
        return buckets

    def query_token_activity(self, time_range: HistoryRange) -> list[TokenActivityPoint]:
        """从精确事件重建范围累计曲线，确保末点与同范围总量完全一致。

        今日使用 5 分钟桶，7 天使用 30 分钟桶，30 天使用 2 小时桶。
        序列从范围起点的零值开始，并补齐空桶；没有请求的时段会保持水平，
        不会再把采集器运行快照的缺口误显示成 Token 数据缺失。
        """

        now = datetime.now(timezone.utc)
        start = calendar_range_start(time_range, now)
        bucket_seconds = _RANGE_CONFIG[time_range][1]
        start_text = self._serialize_time(start)
        end_text = self._serialize_time(now)
        increments: dict[int, dict[str, int]] = {}

        with self._connect() as connection:
            codex_rows = connection.execute(
                """
                SELECT timestamp, total_tokens AS tokens
                FROM codex_usage_events
                WHERE timestamp >= ? AND timestamp <= ?
                """,
                (start_text, end_text),
            ).fetchall()
            ollama_rows = connection.execute(
                """
                SELECT timestamp, prompt_tokens + completion_tokens AS tokens
                FROM ollama_usage_events
                WHERE timestamp >= ? AND timestamp <= ?
                    AND status = 'completed' AND metric_precision = 'exact'
                """,
                (start_text, end_text),
            ).fetchall()
            antigravity_rows = connection.execute(
                """
                SELECT timestamp, total_tokens AS tokens
                FROM antigravity_usage_events
                WHERE timestamp >= ? AND timestamp <= ?
                """,
                (start_text, end_text),
            ).fetchall()

        # 处理：按相对范围起点分桶，可避免 SQLite 时区函数与本地自然日起点产生偏差。
        for provider, rows in (("codex", codex_rows), ("ollama", ollama_rows), ("antigravity", antigravity_rows)):
            for row in rows:
                timestamp = datetime.fromisoformat(row["timestamp"]).astimezone(timezone.utc)
                bucket_index = max(
                    0,
                    int((timestamp - start).total_seconds() // bucket_seconds),
                )
                values = increments.setdefault(
                    bucket_index,
                    {"ollama": 0, "codex": 0, "antigravity": 0},
                )
                values[provider] += int(row["tokens"])

        elapsed_seconds = max(0.0, (now - start).total_seconds())
        last_bucket = int(elapsed_seconds // bucket_seconds)
        ollama_total = 0
        codex_total = 0
        antigravity_total = 0
        points = [
            TokenActivityPoint(
                timestamp=start,
                ollama_tokens=0,
                codex_tokens=0,
                antigravity_tokens=0,
            )
        ]
        for bucket_index in range(last_bucket + 1):
            values = increments.get(bucket_index, {"ollama": 0, "codex": 0, "antigravity": 0})
            ollama_total += values["ollama"]
            codex_total += values["codex"]
            antigravity_total += values["antigravity"]
            bucket_end = min(
                now,
                start + timedelta(seconds=(bucket_index + 1) * bucket_seconds),
            )
            points.append(
                TokenActivityPoint(
                    timestamp=bucket_end,
                    ollama_tokens=ollama_total,
                    codex_tokens=codex_total,
                    antigravity_tokens=antigravity_total,
                )
            )
        return points

    def get_ollama_usage_summary(self) -> OllamaUsageSummary:
        """按本地自然日汇总精确 token，并区分全部尝试与精确完成请求。"""

        # 口径：界面中的 24H 与 Codex 保持一致，代表“本地今天”；
        # 7D/30D 均包含今天，边界先转为 UTC 后再查询统一存储的时间戳。
        now = datetime.now(timezone.utc)
        today_start = self._serialize_time(calendar_range_start("24H", now))
        yesterday = datetime.combine(now.astimezone().date() - timedelta(days=1), datetime.min.time()).astimezone()
        yesterday_start = self._serialize_time(yesterday)
        seven_day_start = self._serialize_time(calendar_range_start("7D", now))
        thirty_day_start = self._serialize_time(calendar_range_start("30D", now))
        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND status = 'completed'
                        AND metric_precision = 'exact'
                        THEN prompt_tokens ELSE 0 END), 0) AS input_tokens,
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND status = 'completed'
                        AND metric_precision = 'exact'
                        THEN completion_tokens ELSE 0 END), 0) AS output_tokens,
                    COALESCE(SUM(CASE WHEN timestamp >= ?
                        THEN 1 ELSE 0 END), 0) AS requests_today,
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND status = 'completed'
                        AND metric_precision = 'exact' THEN 1 ELSE 0 END), 0)
                        AS completed_requests_today,
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND timestamp < ?
                        AND status = 'completed' AND metric_precision = 'exact'
                        THEN prompt_tokens + completion_tokens ELSE 0 END), 0)
                        AS previous_day_tokens,
                    COALESCE(SUM(CASE WHEN timestamp >= ?
                        AND status = 'completed' AND metric_precision = 'exact'
                        THEN prompt_tokens + completion_tokens ELSE 0 END), 0)
                        AS tokens_7d,
                    COALESCE(SUM(CASE WHEN timestamp >= ?
                        AND status = 'completed' AND metric_precision = 'exact'
                        THEN prompt_tokens ELSE 0 END), 0) AS input_tokens_7d,
                    COALESCE(SUM(CASE WHEN timestamp >= ?
                        AND status = 'completed' AND metric_precision = 'exact'
                        THEN completion_tokens ELSE 0 END), 0) AS output_tokens_7d,
                    COALESCE(SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END), 0)
                        AS requests_7d,
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND status = 'completed'
                        AND metric_precision = 'exact' THEN 1 ELSE 0 END), 0)
                        AS completed_requests_7d,
                    COALESCE(SUM(CASE WHEN timestamp >= ?
                        AND status = 'completed' AND metric_precision = 'exact'
                        THEN prompt_tokens + completion_tokens ELSE 0 END), 0)
                        AS tokens_30d,
                    COALESCE(SUM(CASE WHEN timestamp >= ?
                        AND status = 'completed' AND metric_precision = 'exact'
                        THEN prompt_tokens ELSE 0 END), 0) AS input_tokens_30d,
                    COALESCE(SUM(CASE WHEN timestamp >= ?
                        AND status = 'completed' AND metric_precision = 'exact'
                        THEN completion_tokens ELSE 0 END), 0) AS output_tokens_30d,
                    COALESCE(SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END), 0)
                        AS requests_30d,
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND status = 'completed'
                        AND metric_precision = 'exact' THEN 1 ELSE 0 END), 0)
                        AS completed_requests_30d
                FROM ollama_usage_events
                WHERE timestamp <= ?
                """,
                (
                    today_start,
                    today_start,
                    today_start,
                    today_start,
                    yesterday_start,
                    today_start,
                    seven_day_start,
                    seven_day_start,
                    seven_day_start,
                    seven_day_start,
                    seven_day_start,
                    thirty_day_start,
                    thirty_day_start,
                    thirty_day_start,
                    thirty_day_start,
                    thirty_day_start,
                    self._serialize_time(now),
                ),
            ).fetchone()
            latest = connection.execute(
                """
                SELECT model, prompt_tokens, tokens_per_second, timestamp
                FROM ollama_usage_events
                WHERE status = 'completed' AND metric_precision = 'exact'
                    AND timestamp <= ?
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                (self._serialize_time(now),),
            ).fetchone()
            latest_request = connection.execute(
                """SELECT model, timestamp FROM ollama_usage_events
                WHERE timestamp <= ? ORDER BY timestamp DESC, id DESC LIMIT 1""",
                (self._serialize_time(now),),
            ).fetchone()

        input_tokens = int(totals["input_tokens"])
        output_tokens = int(totals["output_tokens"])
        return OllamaUsageSummary(
            model=str(latest_request["model"]) if latest_request else "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            tokens_per_second=float(latest["tokens_per_second"]) if latest else 0.0,
            context_used=int(latest["prompt_tokens"]) if latest else 0,
            requests_today=int(totals["requests_today"]),
            completed_requests_today=int(totals["completed_requests_today"]),
            previous_day_tokens=int(totals["previous_day_tokens"]),
            tokens_7d=int(totals["tokens_7d"]),
            tokens_30d=int(totals["tokens_30d"]),
            range_usage={
                "24H": UsageBreakdown(
                    total_tokens=input_tokens + output_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    interactions=int(totals["requests_today"]),
                    exact_completions=int(totals["completed_requests_today"]),
                ),
                "7D": UsageBreakdown(
                    total_tokens=int(totals["tokens_7d"]),
                    input_tokens=int(totals["input_tokens_7d"]),
                    output_tokens=int(totals["output_tokens_7d"]),
                    interactions=int(totals["requests_7d"]),
                    exact_completions=int(totals["completed_requests_7d"]),
                ),
                "30D": UsageBreakdown(
                    total_tokens=int(totals["tokens_30d"]),
                    input_tokens=int(totals["input_tokens_30d"]),
                    output_tokens=int(totals["output_tokens_30d"]),
                    interactions=int(totals["requests_30d"]),
                    exact_completions=int(totals["completed_requests_30d"]),
                ),
            },
            last_request_at=latest_request["timestamp"] if latest_request else None,
        )

    def query_ollama_requests(self, limit: int = 50) -> list[dict[str, object]]:
        """返回匿名请求结果；失败和无 usage 的请求保留状态，不伪造精确用量。"""

        with self._connect() as connection:
            rows = connection.execute(
                """SELECT timestamp, request_id, endpoint, model, prompt_tokens,
                completion_tokens,
                CASE WHEN eval_duration_ns > 0 THEN tokens_per_second ELSE NULL END AS tokens_per_second,
                status, http_status,
                metric_precision, error_type FROM ollama_usage_events
                WHERE timestamp <= ?
                ORDER BY timestamp DESC, id DESC LIMIT ?""",
                (self._serialize_time(datetime.now(timezone.utc)), max(1, min(limit, 200))),
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        """创建短生命周期连接，并启用适合本地监控写读并发的 WAL。"""

        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @staticmethod
    def _signal_insert_sql() -> str:
        """统一事件插入语句，避免采样写入与即时事件写入产生字段漂移。"""

        return """
            INSERT INTO signal_events (
                timestamp, source, event, detail, severity
            ) VALUES (?, ?, ?, ?, ?)
        """

    def _signal_rows(self, signals: list[SignalEvent]) -> list[tuple[object, ...]]:
        """把事件模型转换为 SQLite 参数，不包含任何提示词或回复正文。"""

        return [
            (
                self._serialize_time(signal.timestamp),
                signal.source,
                signal.event,
                signal.detail,
                signal.severity,
            )
            for signal in signals
        ]

    def _prune_if_due(self, connection: sqlite3.Connection) -> None:
        """最多每小时执行一次保留清理，避免两秒采集循环频繁 DELETE。"""

        now = time.monotonic()
        if now - self._last_prune_at < 3600:
            return
        cutoff = self._serialize_time(
            datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        )
        connection.execute("DELETE FROM trend_points WHERE timestamp < ?", (cutoff,))
        connection.execute("DELETE FROM signal_events WHERE timestamp < ?", (cutoff,))
        connection.execute(
            "DELETE FROM ollama_usage_events WHERE timestamp < ?", (cutoff,)
        )
        connection.execute(
            "DELETE FROM codex_usage_events WHERE timestamp < ?", (cutoff,)
        )
        connection.execute(
            "DELETE FROM antigravity_usage_events WHERE timestamp < ?", (cutoff,)
        )
        self._last_prune_at = now

    @staticmethod
    def _serialize_time(value: datetime) -> str:
        """统一转换为可按字符串排序的 UTC ISO 时间。"""

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds")
