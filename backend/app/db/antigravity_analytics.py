"""Antigravity 匿名事件账本分析。"""

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
)


def _empty_usage() -> dict[str, Any]:
    """创建内部聚合容器。"""
    return {
        **{field: 0 for field in _TOKEN_FIELDS},
        "completions": 0,
        "sessions": set(),
    }


def _add_usage(target: dict[str, Any], row: dict[str, Any]) -> None:
    """把单条匿名事件累加到维度容器。"""
    for field in _TOKEN_FIELDS:
        target[field] += int(row[field])
    target["completions"] += 1
    target["sessions"].add(row["session_id"])


def _public_usage(target: dict[str, Any]) -> dict[str, Any]:
    """返回可 JSON 序列化的统一指标。"""
    return {
        **{field: int(target[field]) for field in _TOKEN_FIELDS},
        "completions": int(target["completions"]),
        "sessions": len(target["sessions"]),
    }


def query_antigravity_analytics(
    repository: HistoryRepository,
    time_range: HistoryRange,
) -> dict[str, object]:
    """按与 Codex 相同口径返回 Antigravity 账本的模型、工作区与会话分析。"""
    now = datetime.now().astimezone()
    start = calendar_range_start(time_range, now)

    with repository._connect() as connection:
        connection.row_factory = sqlite3.Row
        watermark = connection.execute(
            "SELECT COALESCE(MAX(id), 0) FROM antigravity_usage_events"
        ).fetchone()[0]

        start_text = repository._serialize_time(start)
        end_text = repository._serialize_time(now)

        rows = connection.execute(
            """
            SELECT id, timestamp, session_id, model, workspace_label,
                   input_tokens, output_tokens, cached_tokens, total_tokens
            FROM antigravity_usage_events
            WHERE timestamp >= ? AND timestamp <= ? AND id <= ?
            ORDER BY timestamp ASC, id ASC
            """,
            (start_text, end_text, watermark),
        ).fetchall()

    totals = _empty_usage()
    models: dict[str, dict[str, Any]] = {}
    workspaces: dict[str, dict[str, Any]] = {}
    sessions: dict[str, dict[str, Any]] = {}
    daily: dict[str, dict[str, Any]] = {}

    for row in rows:
        _add_usage(totals, row)

        model_name = str(row["model"] or "Unknown")
        model_usage = models.setdefault(
            model_name,
            {**_empty_usage(), "model": model_name},
        )
        _add_usage(model_usage, row)

        ws_label = str(row["workspace_label"] or "Unassigned")
        ws_usage = workspaces.setdefault(
            ws_label,
            {**_empty_usage(), "workspace": ws_label, "workspace_id": ws_label, "last_active": row["timestamp"]},
        )
        _add_usage(ws_usage, row)
        ws_usage["last_active"] = row["timestamp"]

        sess_id = str(row["session_id"])
        sess_usage = sessions.setdefault(
            sess_id,
            {
                **_empty_usage(),
                "session_id": sess_id,
                "session": f"AG-{sess_id[:8].upper()}",
                "model": model_name,
                "workspace": ws_label,
                "last_active": row["timestamp"],
            },
        )
        _add_usage(sess_usage, row)
        sess_usage["last_active"] = row["timestamp"]

        local_day = datetime.fromisoformat(str(row["timestamp"])).astimezone().date().isoformat()
        day_usage = daily.setdefault(local_day, {**_empty_usage(), "day": local_day})
        _add_usage(day_usage, row)

    total_tokens = int(totals["total_tokens"])

    model_rows = []
    for val in models.values():
        pub = _public_usage(val)
        model_rows.append({
            "model": val["model"],
            **pub,
            "share_percent": (pub["total_tokens"] / total_tokens * 100) if total_tokens else 0,
        })
    model_rows.sort(key=lambda x: (-x["total_tokens"], x["model"]))

    workspace_rows = []
    for val in workspaces.values():
        pub = _public_usage(val)
        workspace_rows.append({
            "workspace_id": val["workspace_id"],
            "workspace": val["workspace"],
            "last_active": val["last_active"],
            **pub,
            "share_percent": (pub["total_tokens"] / total_tokens * 100) if total_tokens else 0,
        })
    workspace_rows.sort(key=lambda x: (-x["total_tokens"], x["workspace"]))

    session_rows = []
    for val in sessions.values():
        pub = _public_usage(val)
        session_rows.append({
            "session_id": val["session_id"],
            "session": val["session"],
            "model": val["model"],
            "workspace_id": val["workspace"],
            "workspace": val["workspace"],
            "last_active": val["last_active"],
            **pub,
            "share_percent": (pub["total_tokens"] / total_tokens * 100) if total_tokens else 0,
        })
    session_rows.sort(key=lambda x: (-x["total_tokens"], x["session"]))

    daily_rows = []
    day = start.astimezone().date()
    end_day = now.astimezone().date()
    while day <= end_day:
        key = day.isoformat()
        val = daily.get(key, {**_empty_usage(), "day": key})
        daily_rows.append({"day": key, **_public_usage(val)})
        day += timedelta(days=1)

    summary = _public_usage(totals)
    summary.update({
        "models": len([k for k in models if k]),
        "workspaces": len([k for k in workspaces if k]),
        "cache_ratio": (
            (summary["cached_tokens"] / (summary["input_tokens"] + summary["cached_tokens"]) * 100)
            if (summary["input_tokens"] + summary["cached_tokens"]) > 0
            else 0
        ),
    })

    return {
        "provider": "antigravity",
        "range": time_range,
        "start": start.isoformat(),
        "local_start": start.astimezone().isoformat(),
        "local_end": now.astimezone().isoformat(),
        "updated_at": now.isoformat(),
        "snapshot_id": watermark,
        "summary": summary,
        "models": model_rows[:8],
        "workspaces": workspace_rows[:8],
        "sessions": session_rows[:12],
        "daily": daily_rows,
    }
