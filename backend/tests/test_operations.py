"""运营指标验证：范围、缺失值、筛选和分页不能改变统计口径。"""

from datetime import datetime, timedelta, timezone
import csv
import io

from app.core.time_ranges import calendar_range_start
from app.db.history import HistoryRepository
from app.db.operations import operations_csv, query_operations
from app.schemas.dashboard import OllamaUsageEvent


def record(repository, request_id, **values):
    repository.save_ollama_usage(OllamaUsageEvent(
        request_id=request_id, model=values.pop("model", "test"), endpoint="/api/chat", **values
    ))


def test_metrics_exclude_unknown_usage_and_duration(tmp_path):
    repository = HistoryRepository(tmp_path / "ops.db")
    repository.initialize()
    record(repository, "exact", prompt_tokens=100, completion_tokens=50, total_duration_ns=2_000_000_000)
    record(repository, "usage-only", prompt_tokens=10, completion_tokens=20)
    record(repository, "failed", status="failed", metric_precision="unavailable", prompt_tokens=999)
    record(repository, "unknown", status="unmetered", metric_precision="unavailable")
    record(repository, "cancelled", status="cancelled", metric_precision="unavailable")
    data = query_operations(repository, "24H")
    assert data["summary"]["requests"] == 5
    assert data["summary"]["success_rate"] == 60
    assert data["summary"]["input_tokens"] == 110
    assert data["summary"]["output_tokens"] == 70
    assert data["summary"]["avg_duration_seconds"] == 2
    assert data["summary"]["p95_duration_seconds"] == 2
    assert data["summary"]["duration_samples"] == 1
    assert data["models"][0]["tokens"] == 180
    assert sum(point["input_tokens"] + point["output_tokens"] for point in data["series"]) == 180
    assert sum(point["requests"] for point in data["performance_series"]) == 5
    active_performance = [point for point in data["performance_series"] if point["requests"]]
    assert active_performance[-1]["success_rate"] == 60
    assert active_performance[-1]["p95_duration_seconds"] == 2
    rows = {row["request_id"]: row for row in data["requests"]}
    assert rows["failed"]["input_tokens"] is None
    assert rows["usage-only"]["duration_seconds"] is None
    assert rows["usage-only"]["tokens_per_second"] is None


def test_range_filters_empty_state_and_frozen_pages(tmp_path):
    repository = HistoryRepository(tmp_path / "ops.db")
    repository.initialize()
    for index in range(23):
        record(repository, f"request-{index}", prompt_tokens=1)
    yesterday = calendar_range_start("24H") - timedelta(seconds=1)
    record(repository, "old", timestamp=yesterday, model="other", prompt_tokens=50)
    record(repository, "future", timestamp=datetime.now(timezone.utc) + timedelta(days=1))
    first = query_operations(repository, "24H", page_size=20)
    record(repository, "new", prompt_tokens=2)
    second = query_operations(repository, "24H", page=2, page_size=20, snapshot_id=first["snapshot_id"])
    assert first["summary"]["requests"] == second["summary"]["requests"] == 23
    assert len(second["requests"]) == 3
    assert not {r["request_id"] for r in first["requests"]} & {r["request_id"] for r in second["requests"]}
    assert query_operations(repository, "7D")["summary"]["input_tokens"] == 75
    assert len(query_operations(repository, "7D")["series"]) == 7
    assert len(query_operations(repository, "7D")["performance_series"]) == 7
    assert query_operations(repository, "7D", model="other")["summary"]["requests"] == 1
    assert query_operations(repository, "24H", search="request-2")["summary"]["requests"] == 4
    empty = query_operations(repository, "24H", search="%' OR 1=1 --")
    assert empty["summary"]["requests"] == 0
    assert empty["summary"]["success_rate"] is None
    assert empty["summary"]["avg_duration_seconds"] is None
    assert empty["page_count"] == 1


def test_p95_uses_nearest_rank_and_status_filters(tmp_path):
    repository = HistoryRepository(tmp_path / "ops.db")
    repository.initialize()
    for index in range(1, 21):
        record(repository, str(index), total_duration_ns=index * 1_000_000_000)
    record(repository, "failure", status="failed", total_duration_ns=900_000_000_000)
    data = query_operations(repository, "24H")
    assert data["summary"]["p95_duration_seconds"] == 19
    assert data["summary"]["avg_duration_seconds"] == 10.5
    failed = query_operations(repository, "24H", status="failed")
    assert failed["summary"]["requests"] == 1
    assert failed["summary"]["success_rate"] == 0
    assert failed["summary"]["avg_duration_seconds"] is None


def test_csv_preserves_missing_values_and_blocks_formula_injection():
    content = operations_csv([{"model": '=SUM(1,2)', "endpoint": '/api/"chat"',
                               "input_tokens": None, "output_tokens": 0}])
    assert content.startswith("\ufeff")
    row = next(csv.DictReader(io.StringIO(content.lstrip("\ufeff"))))
    assert row["model"] == "'=SUM(1,2)"
    assert row["endpoint"] == '/api/"chat"'
    assert row["input_tokens"] == ""
    assert row["output_tokens"] == "0"
