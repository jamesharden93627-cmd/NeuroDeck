"""请求运营分析：同一次只读事务内计算指标、排行、趋势和分页。"""

from datetime import datetime, timedelta, timezone
from math import ceil
import csv
import io

from app.core.time_ranges import calendar_range_start
from app.db.history import HistoryRange, HistoryRepository


def _performance_series(
    rows: list[dict[str, object]], start: datetime, now: datetime, time_range: HistoryRange,
) -> list[dict[str, object]]:
    """按小时或自然日汇总请求质量；缺失耗时与速度不作为零值参与平均。"""

    buckets: dict[str, dict[str, object]] = {}
    for row in rows:
        local_time = datetime.fromisoformat(str(row["timestamp"])).astimezone()
        key = (
            local_time.replace(minute=0, second=0, microsecond=0).isoformat()
            if time_range == "24H"
            else local_time.date().isoformat()
        )
        bucket = buckets.setdefault(key, {"requests": 0, "succeeded": 0, "durations": [], "speeds": []})
        bucket["requests"] = int(bucket["requests"]) + 1
        if row["status"] in ("completed", "unmetered"):
            bucket["succeeded"] = int(bucket["succeeded"]) + 1
        if row["status"] == "completed" and int(row["total_duration_ns"] or 0) > 0:
            bucket["durations"].append(int(row["total_duration_ns"]) / 1e9)
        if row["status"] == "completed" and int(row["eval_duration_ns"] or 0) > 0:
            bucket["speeds"].append(float(row["tokens_per_second"] or 0))

    def public(timestamp: str, bucket: dict[str, object]) -> dict[str, object]:
        """把内部样本数组转换为前端可直接绘制的聚合点。"""

        requests = int(bucket["requests"])
        succeeded = int(bucket["succeeded"])
        durations = sorted(float(value) for value in bucket["durations"])
        speeds = [float(value) for value in bucket["speeds"]]
        return {
            "timestamp": timestamp,
            "requests": requests,
            "succeeded": succeeded,
            "other_outcomes": requests - succeeded,
            "success_rate": succeeded / requests * 100 if requests else None,
            "avg_duration_seconds": sum(durations) / len(durations) if durations else None,
            "p95_duration_seconds": durations[ceil(len(durations) * .95) - 1] if durations else None,
            "duration_samples": len(durations),
            "avg_tokens_per_second": sum(speeds) / len(speeds) if speeds else None,
            "speed_samples": len(speeds),
        }

    empty = {"requests": 0, "succeeded": 0, "durations": [], "speeds": []}
    result = []
    if time_range == "24H":
        cursor = start.astimezone().replace(minute=0, second=0, microsecond=0)
        end = now.astimezone().replace(minute=0, second=0, microsecond=0)
        while cursor <= end:
            timestamp = cursor.isoformat()
            result.append(public(timestamp, buckets.get(timestamp, empty)))
            cursor += timedelta(hours=1)
        return result

    day = start.astimezone().date()
    end_day = now.astimezone().date()
    while day <= end_day:
        key = day.isoformat()
        timestamp = datetime.combine(day, datetime.min.time()).astimezone().isoformat()
        result.append(public(timestamp, buckets.get(key, empty)))
        day += timedelta(days=1)
    return result


def operations_csv(records: list[dict[str, object]]) -> str:
    """导出当前页匿名指标；保留未知值为空并转义外部模型名的表格公式前缀。"""

    columns = ["request_id", "timestamp", "model", "endpoint", "status", "http_status",
               "input_tokens", "output_tokens", "duration_seconds", "tokens_per_second",
               "metric_precision", "error_type"]
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    for record in records:
        values = []
        for column in columns:
            value = record.get(column)
            if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return "\ufeff" + output.getvalue()


def query_operations(
    repository: HistoryRepository, time_range: HistoryRange, model: str = "",
    status: str = "", search: str = "", page: int = 1, page_size: int = 20,
    snapshot_id: int | None = None,
) -> dict[str, object]:
    """返回 Ollama 请求分析；未上报的耗时与用量保持为空，分页固定记录水位。"""

    now = datetime.now(timezone.utc)
    start = calendar_range_start(time_range, now)
    with repository._connect() as connection:
        # 处理：锁定读取快照；翻页复用水位，避免新请求插入造成重复或漏行。
        connection.execute("BEGIN")
        latest_id = connection.execute("SELECT COALESCE(MAX(id), 0) FROM ollama_usage_events").fetchone()[0]
        watermark = min(snapshot_id, latest_id) if snapshot_id is not None else latest_id
        base = "timestamp >= ? AND timestamp <= ? AND id <= ?"
        params: list[object] = [repository._serialize_time(start), repository._serialize_time(now), watermark]
        options = [row[0] for row in connection.execute(
            f"SELECT DISTINCT model FROM ollama_usage_events WHERE {base} "
            "AND model <> '' ORDER BY model", params
        )]
        where = base
        for field, value in (("model", model), ("status", status)):
            if value:
                where += f" AND {field} = ?"
                params.append(value)
        if search:
            # 功能：字面子串匹配请求 ID，不把用户输入中的 SQL 通配符当作语法。
            where += " AND instr(request_id, ?) > 0"
            params.append(search)

        measured = "status = 'completed' AND metric_precision = 'exact'"
        success = "status IN ('completed', 'unmetered')"
        timed = "status = 'completed' AND total_duration_ns > 0"
        summary = dict(connection.execute(f"""
            SELECT COUNT(*) AS requests,
                COALESCE(SUM({success}), 0) AS succeeded,
                COALESCE(SUM(status = 'failed'), 0) AS failed,
                COALESCE(SUM(status = 'cancelled'), 0) AS cancelled,
                COALESCE(SUM(status = 'incomplete'), 0) AS incomplete,
                COALESCE(SUM({measured}), 0) AS metered,
                COALESCE(SUM(CASE WHEN {measured} THEN prompt_tokens ELSE 0 END), 0) AS input_tokens,
                COALESCE(SUM(CASE WHEN {measured} THEN completion_tokens ELSE 0 END), 0) AS output_tokens,
                AVG(CASE WHEN {timed} THEN total_duration_ns / 1e9 END) AS avg_duration_seconds,
                COALESCE(SUM({timed}), 0) AS duration_samples
            FROM ollama_usage_events WHERE {where}
        """, params).fetchone())
        summary["success_rate"] = summary["succeeded"] / summary["requests"] * 100 if summary["requests"] else None
        summary["p95_duration_seconds"] = None
        if summary["duration_samples"]:
            summary["p95_duration_seconds"] = connection.execute(
                f"SELECT total_duration_ns / 1e9 FROM ollama_usage_events WHERE {where} AND {timed} "
                "ORDER BY total_duration_ns LIMIT 1 OFFSET ?",
                [*params, ceil(summary["duration_samples"] * .95) - 1],
            ).fetchone()[0]

        models = [dict(row) for row in connection.execute(f"""
            SELECT model, COUNT(*) AS requests,
                COALESCE(SUM({success}), 0) AS succeeded,
                COALESCE(SUM(CASE WHEN {measured} THEN prompt_tokens + completion_tokens ELSE 0 END), 0) AS tokens
            FROM ollama_usage_events WHERE {where}
            GROUP BY model ORDER BY tokens DESC, requests DESC, model LIMIT 10
        """, params)]
        # 口径：按本机自然日统计请求增量，补齐没有请求的日期，而不是累计快照。
        daily = {row["day"]: dict(row) for row in connection.execute(f"""
            SELECT date(timestamp, 'localtime') AS day, COUNT(*) AS requests,
                COALESCE(SUM(CASE WHEN {measured} THEN prompt_tokens ELSE 0 END), 0) AS input_tokens,
                COALESCE(SUM(CASE WHEN {measured} THEN completion_tokens ELSE 0 END), 0) AS output_tokens
            FROM ollama_usage_events WHERE {where} GROUP BY day ORDER BY day
        """, params)}
        series = []
        day = start.astimezone().date()
        while day <= now.astimezone().date():
            key = day.isoformat()
            series.append(daily.get(key, {"day": key, "requests": 0, "input_tokens": 0, "output_tokens": 0}))
            day += timedelta(days=1)

        # 功能：只提取绘图所需数值，不读取或保存请求正文。
        performance_rows = [dict(row) for row in connection.execute(f"""
            SELECT timestamp, status, total_duration_ns, eval_duration_ns, tokens_per_second
            FROM ollama_usage_events WHERE {where}
            ORDER BY timestamp ASC, id ASC
        """, params)]
        performance_series = _performance_series(performance_rows, start, now, time_range)

        page_count = max(1, ceil(summary["requests"] / page_size))
        page = min(page, page_count)
        requests = [dict(row) for row in connection.execute(f"""
            SELECT request_id, timestamp, model, endpoint, status, http_status, metric_precision, error_type,
                CASE WHEN {measured} THEN prompt_tokens END AS input_tokens,
                CASE WHEN {measured} THEN completion_tokens END AS output_tokens,
                CASE WHEN {timed} THEN total_duration_ns / 1e9 END AS duration_seconds,
                CASE WHEN status = 'completed' AND eval_duration_ns > 0 THEN tokens_per_second END AS tokens_per_second
            FROM ollama_usage_events WHERE {where}
            ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?
        """, [*params, page_size, (page - 1) * page_size])]

    return {"provider": "ollama", "range": time_range, "start": start.isoformat(),
            "updated_at": now.isoformat(), "snapshot_id": watermark, "summary": summary,
            "models": models, "model_options": options, "series": series, "requests": requests,
            "performance_series": performance_series,
            "page": page, "page_size": page_size, "page_count": page_count}
