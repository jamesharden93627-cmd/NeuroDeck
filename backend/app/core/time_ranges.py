"""统一本机自然日范围，供 KPI、历史查询和浏览器时间轴共享。"""

from datetime import datetime, timedelta, timezone


def calendar_range_start(time_range: str, now: datetime | None = None) -> datetime:
    """返回包含今天的 1/7/30 天起点（UTC）；按目标日期计算本地偏移以适配夏令时。"""

    local = (now or datetime.now(timezone.utc)).astimezone()
    days = {"24H": 1, "7D": 7, "30D": 30}[time_range]
    day = local.date() - timedelta(days=days - 1)
    return datetime.combine(day, datetime.min.time()).astimezone(timezone.utc)


def calendar_range_starts() -> dict[str, datetime]:
    """一次取时，保证跨午夜时三个范围仍属于同一天。"""

    now = datetime.now(timezone.utc)
    return {key: calendar_range_start(key, now) for key in ("24H", "7D", "30D")}
