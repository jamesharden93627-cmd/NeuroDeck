"""自然日起点、历史边界与健康状态的确定性回归。"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.time_ranges import calendar_range_start
from app.db.history import HistoryRepository
from app.schemas.dashboard import TrendPoint
from app.services.dashboard import DashboardService


def test_calendar_range_counts_inclusive_local_days() -> None:
    now = datetime.now(timezone.utc)
    today = now.astimezone().date()
    for key, offset in (("24H", 0), ("7D", 6), ("30D", 29)):
        start = calendar_range_start(key, now).astimezone()
        assert start.date() == today - timedelta(days=offset)
        assert (start.hour, start.minute, start.second) == (0, 0, 0)


def test_history_excludes_yesterday_from_today_and_future(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "calendar.db")
    repository.initialize()
    start = calendar_range_start("24H")
    now = datetime.now(timezone.utc)
    for timestamp, tokens in ((start - timedelta(seconds=1), 10), (now, 20), (now + timedelta(days=1), 30)):
        repository.save_sample(TrendPoint(timestamp=timestamp, codex_tokens=tokens), [])
    points = repository.query_history("24H")
    assert len(points) == 1
    assert points[0].codex_tokens == 20


def test_health_detects_stale_collector_and_storage_failure() -> None:
    service = DashboardService(None, None, None)
    assert asyncio.run(service.health())["collector"] == "unknown"
    service._latest = SimpleNamespace(timestamp=datetime.now(timezone.utc))
    assert asyncio.run(service.health())["status"] == "ok"
    service._latest.timestamp -= timedelta(seconds=20)
    assert asyncio.run(service.health())["collector"] == "stale"
    service._storage_healthy = False
    assert asyncio.run(service.health())["storage"] == "degraded"
