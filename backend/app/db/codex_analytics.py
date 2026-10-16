"""Codex 匿名事件账本分析。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import sqlite3

from app.core.time_ranges import calendar_range_start
from app.db.history import HistoryRange, HistoryRepository


_TOKEN_FIELDS = (
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
)


def _empty_usage() -> dict[str, Any]:
    """创建内部聚合容器；下划线字段仅用于计算，不会返回前端。"""

    return {
        **{field: 0 for field in _TOKEN_FIELDS},
        "completions": 0,
        "sessions": set(),
    }


def _add_usage(target: dict[str, Any], row: dict[str, Any]) -> None:
    """把单条匿名事件累加到模型、工作区、会话或日期维度。"""

    for field in _TOKEN_FIELDS:
        target[field] += int(row[field])
    target["completions"] += 1
    target["sessions"].add(row["session_id"])


def _public_usage(target: dict[str, Any]) -> dict[str, Any]:
    """移除内部集合并返回可 JSON 序列化的统一指标。"""

    return {
        **{field: int(target[field]) for field in _TOKEN_FIELDS},
        "completions": int(target["completions"]),
        "sessions": len(target["sessions"]),
    }


def _period_comparison(
    connection: sqlite3.Connection,
    repository: HistoryRepository,
    now: datetime,
    watermark: int,
) -> list[dict[str, object]]:
    """在同一账本快照中比较自然日与滚动窗口，只返回数值和明确的时区边界。"""

    local_start = calendar_range_start("24H", now)
    utc_start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    windows = [
        ("local_today", local_start, now),
        ("utc_today", utc_start, now),
        ("rolling_24h", now - timedelta(hours=24), now),
    ]
    result = []
    for key, start, end in windows:
        usage = connection.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(activity_tokens), 0) AS activity_tokens,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                COUNT(*) AS events, COUNT(DISTINCT session_id) AS sessions,
                COALESCE(SUM(CASE WHEN activity_tokens > 0 THEN 1 ELSE 0 END), 0) AS activity_events
            FROM codex_usage_events
            WHERE timestamp >= ? AND timestamp <= ? AND id <= ?
            """,
            (repository._serialize_time(start), repository._serialize_time(end), watermark),
        ).fetchone()
        # 口径：UTC 行直接携带 UTC 边界，其他行携带主机本地偏移，浏览器不能自行改日。
        result.append({
            "period": key,
            "start": (start.astimezone(timezone.utc) if key == "utc_today" else start.astimezone()).isoformat(),
            "end": (end.astimezone(timezone.utc) if key == "utc_today" else end.astimezone()).isoformat(),
            **dict(usage),
        })
    return result


def _timeline(rows: list[dict[str, Any]], start: datetime, now: datetime, time_range: HistoryRange) -> list[dict[str, Any]]:
    """按今日小时或长范围自然日生成构成趋势，并显式补齐没有事件的时间桶。"""

    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        local_time = datetime.fromisoformat(str(row["timestamp"])).astimezone()
        key = (
            local_time.replace(minute=0, second=0, microsecond=0).isoformat()
            if time_range == "24H"
            else local_time.date().isoformat()
        )
        usage = buckets.setdefault(key, _empty_usage())
        _add_usage(usage, row)

    result: list[dict[str, Any]] = []
    if time_range == "24H":
        cursor = start.astimezone().replace(minute=0, second=0, microsecond=0)
        end = now.astimezone().replace(minute=0, second=0, microsecond=0)
        while cursor <= end:
            key = cursor.isoformat()
            result.append({"timestamp": key, **_public_usage(buckets.get(key, _empty_usage()))})
            cursor += timedelta(hours=1)
        return result

    day = start.astimezone().date()
    end_day = now.astimezone().date()
    while day <= end_day:
        key = day.isoformat()
        timestamp = datetime.combine(day, datetime.min.time()).astimezone().isoformat()
        result.append({"timestamp": timestamp, **_public_usage(buckets.get(key, _empty_usage()))})
        day += timedelta(days=1)
    return result


def _baseline_comparison(
    connection: sqlite3.Connection,
    repository: HistoryRepository,
    now: datetime,
    watermark: int,
) -> dict[str, int]:
    """一次扫描计算今日、昨日和近 7/30 个自然日均值，避免轮询时重复查询。"""

    today_start = calendar_range_start("24H", now)
    seven_start = calendar_range_start("7D", now)
    thirty_start = calendar_range_start("30D", now)
    local_yesterday = now.astimezone().date() - timedelta(days=1)
    yesterday_start = datetime.combine(local_yesterday, datetime.min.time()).astimezone(timezone.utc)
    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN timestamp >= ? THEN total_tokens ELSE 0 END), 0) AS today_tokens,
            COALESCE(SUM(CASE WHEN timestamp >= ? AND timestamp < ? THEN total_tokens ELSE 0 END), 0) AS yesterday_tokens,
            COALESCE(SUM(CASE WHEN timestamp >= ? THEN total_tokens ELSE 0 END), 0) AS seven_day_tokens,
            COALESCE(SUM(total_tokens), 0) AS thirty_day_tokens
        FROM codex_usage_events
        WHERE timestamp >= ? AND timestamp <= ? AND id <= ?
        """,
        (
            repository._serialize_time(today_start),
            repository._serialize_time(yesterday_start),
            repository._serialize_time(today_start),
            repository._serialize_time(seven_start),
            repository._serialize_time(thirty_start),
            repository._serialize_time(now),
            watermark,
        ),
    ).fetchone()
    values = dict(row)
    return {
        "today_tokens": int(values["today_tokens"]),
        "yesterday_tokens": int(values["yesterday_tokens"]),
        "average_7d_tokens": round(int(values["seven_day_tokens"]) / 7),
        "average_30d_tokens": round(int(values["thirty_day_tokens"]) / 30),
    }


def _activity_heatmap(rows: list[dict[str, Any]]) -> list[dict[str, int]]:
    """把最近 30 个自然日压缩为星期×小时矩阵，空单元也返回以保持图形稳定。"""

    cells: dict[tuple[int, int], dict[str, int]] = {}
    for row in rows:
        local_time = datetime.fromisoformat(str(row["timestamp"])).astimezone()
        cell = cells.setdefault((local_time.weekday(), local_time.hour), {"total_tokens": 0, "events": 0})
        cell["total_tokens"] += int(row["total_tokens"])
        cell["events"] += 1
    return [
        {"weekday": weekday, "hour": hour, **cells.get((weekday, hour), {"total_tokens": 0, "events": 0})}
        for weekday in range(7)
        for hour in range(24)
    ]


def query_codex_analytics(
    repository: HistoryRepository,
    time_range: HistoryRange,
) -> dict[str, object]:
    """在同一只读事务内生成 Codex 模型、工作区、会话和每日分析。"""

    now = datetime.now(timezone.utc)
    start = calendar_range_start(time_range, now)
    start_text = repository._serialize_time(start)
    end_text = repository._serialize_time(now)

    with repository._connect() as connection:
        connection.execute("BEGIN")
        watermark = int(connection.execute(
            "SELECT COALESCE(MAX(id), 0) FROM codex_usage_events"
        ).fetchone()[0])
        rows = [dict(row) for row in connection.execute(
            """
            SELECT id, timestamp, session_id, model, workspace_id, workspace_label,
                input_tokens, output_tokens, cached_tokens, reasoning_tokens, total_tokens
            FROM codex_usage_events
            WHERE timestamp >= ? AND timestamp <= ? AND id <= ?
            ORDER BY timestamp ASC, id ASC
            """,
            (start_text, end_text, watermark),
        )]
        comparisons = _period_comparison(connection, repository, now, watermark)
        baselines = _baseline_comparison(connection, repository, now, watermark)
        heatmap_rows = [dict(row) for row in connection.execute(
            """
            SELECT timestamp, total_tokens
            FROM codex_usage_events
            WHERE timestamp >= ? AND timestamp <= ? AND id <= ?
            ORDER BY timestamp ASC, id ASC
            """,
            (repository._serialize_time(calendar_range_start("30D", now)), end_text, watermark),
        )]

    totals = _empty_usage()
    models: dict[str, dict[str, Any]] = {}
    workspaces: dict[str, dict[str, Any]] = {}
    sessions: dict[str, dict[str, Any]] = {}
    daily: dict[str, dict[str, Any]] = {}

    for row in rows:
        _add_usage(totals, row)
        model_key = str(row["model"] or "")
        workspace_key = str(row["workspace_id"] or "")
        workspace_label = str(row["workspace_label"] or "")
        local_day = datetime.fromisoformat(str(row["timestamp"])).astimezone().date().isoformat()

        model_usage = models.setdefault(model_key, {**_empty_usage(), "model": model_key})
        _add_usage(model_usage, row)

        workspace_usage = workspaces.setdefault(
            workspace_key,
            {
                **_empty_usage(),
                "workspace_id": workspace_key,
                "workspace": workspace_label,
                "last_active": row["timestamp"],
            },
        )
        _add_usage(workspace_usage, row)
        workspace_usage["last_active"] = row["timestamp"]
        if workspace_label:
            workspace_usage["workspace"] = workspace_label

        session_key = str(row["session_id"])
        session_usage = sessions.setdefault(
            session_key,
            {
                **_empty_usage(),
                "session_id": session_key,
                "session": f"S-{session_key[:8].upper()}",
                "last_active": row["timestamp"],
                "_model_tokens": {},
                "_workspace_tokens": {},
                "_workspace_labels": {},
            },
        )
        _add_usage(session_usage, row)
        session_usage["last_active"] = row["timestamp"]
        session_usage["_model_tokens"][model_key] = (
            session_usage["_model_tokens"].get(model_key, 0) + int(row["total_tokens"])
        )
        session_usage["_workspace_tokens"][workspace_key] = (
            session_usage["_workspace_tokens"].get(workspace_key, 0) + int(row["total_tokens"])
        )
        if workspace_label:
            session_usage["_workspace_labels"][workspace_key] = workspace_label

        daily_usage = daily.setdefault(local_day, {**_empty_usage(), "day": local_day})
        _add_usage(daily_usage, row)

    total_tokens = int(totals["total_tokens"])

    # 功能：排行都使用相同事件水位，切换维度时数值能够互相核对。
    model_rows = []
    for value in models.values():
        public = _public_usage(value)
        model_rows.append({
            "model": value["model"],
            **public,
            "share_percent": public["total_tokens"] / total_tokens * 100 if total_tokens else 0,
        })
    model_rows.sort(key=lambda item: (-item["total_tokens"], item["model"]))

    workspace_rows = []
    for value in workspaces.values():
        public = _public_usage(value)
        workspace_rows.append({
            "workspace_id": value["workspace_id"],
            "workspace": value["workspace"],
            "last_active": value["last_active"],
            **public,
            "share_percent": public["total_tokens"] / total_tokens * 100 if total_tokens else 0,
        })
    workspace_rows.sort(key=lambda item: (-item["total_tokens"], item["workspace"]))

    session_rows = []
    for value in sessions.values():
        model = max(value["_model_tokens"], key=value["_model_tokens"].get, default="")
        workspace_id = max(
            value["_workspace_tokens"],
            key=value["_workspace_tokens"].get,
            default="",
        )
        public = _public_usage(value)
        session_rows.append({
            "session_id": value["session_id"],
            "session": value["session"],
            "model": model,
            "workspace_id": workspace_id,
            "workspace": value["_workspace_labels"].get(workspace_id, ""),
            "last_active": value["last_active"],
            **public,
            "share_percent": public["total_tokens"] / total_tokens * 100 if total_tokens else 0,
        })
    session_rows.sort(key=lambda item: (-item["total_tokens"], item["session"]))

    # 边界：没有事件的自然日也返回零值，后续日趋势不会误把空白压缩掉。
    daily_rows = []
    day = start.astimezone().date()
    end_day = now.astimezone().date()
    while day <= end_day:
        key = day.isoformat()
        value = daily.get(key, {**_empty_usage(), "day": key})
        daily_rows.append({"day": key, **_public_usage(value)})
        day += timedelta(days=1)

    summary = _public_usage(totals)
    summary.update({
        "models": len([key for key in models if key]),
        "workspaces": len([key for key in workspaces if key]),
        "cache_ratio": (
            summary["cached_tokens"] / summary["input_tokens"] * 100
            if summary["input_tokens"] else 0
        ),
    })
    return {
        "provider": "codex",
        "range": time_range,
        "start": start.isoformat(),
        "local_start": start.astimezone().isoformat(),
        "local_end": now.astimezone().isoformat(),
        "period_comparison": comparisons,
        "baseline_comparison": baselines,
        "timeline": _timeline(rows, start, now, time_range),
        "activity_heatmap": _activity_heatmap(heatmap_rows),
        "updated_at": now.isoformat(),
        "snapshot_id": watermark,
        "summary": summary,
        "models": model_rows[:8],
        "workspaces": workspace_rows[:8],
        "sessions": session_rows[:12],
        "daily": daily_rows,
    }
