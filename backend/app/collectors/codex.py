"""只读解析 Codex 本地 session JSONL。"""

from __future__ import annotations

import asyncio
import json
import hashlib
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.collectors.base import BaseCollector
from app.db.history import HistoryRepository
from app.schemas.dashboard import CodexUsageEvent, ProviderSnapshot, UsageBreakdown


class CodexCollector(BaseCollector[ProviderSnapshot]):
    """读取 Codex 已有 token_count 元数据，不读取或保存对话正文。

    解析器容忍未知事件和字段变化。日志格式发生变化时，最坏结果是显示空指标，
    而不是让整个 NeuroDeck 服务崩溃。
    """

    def __init__(
        self,
        codex_home: Path,
        tail_bytes: int = 2_097_152,
        active_window_seconds: float = 30.0,
        history_repository: HistoryRepository | None = None,
    ) -> None:
        self._sessions_root = codex_home / "sessions"
        self._archive_root = codex_home / "archived_sessions"
        self._tail_bytes = tail_bytes
        self._active_window_seconds = max(1.0, active_window_seconds)
        self._history_repository = history_repository
        self._model_cache: dict[Path, str] = {}
        self._workspace_cache: dict[Path, tuple[str, str]] = {}
        # 性能：首次启动扫描现有 token 元数据，后续只读取每个 JSONL 新增的字节。
        self._usage_offsets: dict[Path, int] = {}
        self._daily_usage: dict[date, dict[str, int]] = {}
        self._daily_sessions: dict[date, set[Path]] = {}
        self._session_ids: dict[Path, str] = {}
        self._seen_usage: set[str] = set()
        self._last_usage_state: dict[str, str] = {}
        self._daily_audit: dict[date, dict[str, int]] = {}
        self._pending_usage_events: list[CodexUsageEvent] = []

    async def collect(self) -> ProviderSnapshot:
        """在线程池中扫描最新 session，避免文件 I/O 阻塞事件循环。"""

        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> ProviderSnapshot:
        if not self._sessions_root.exists() and not self._archive_root.exists():
            return self._apply_daily_usage(ProviderSnapshot(
                provider="codex",
                online=False,
                status="offline",
                detail="Codex sessions directory not found",
            ))

        files = list(self._sessions_root.rglob("*.jsonl"))
        files.extend(self._archive_root.rglob("*.jsonl"))
        if not files:
            return self._apply_daily_usage(ProviderSnapshot(
                provider="codex",
                online=True,
                status="idle",
                model="No sessions yet",
                detail="Codex home detected",
            ))

        self._refresh_daily_usage(files)
        latest = max(files, key=lambda path: path.stat().st_mtime)
        rows = self._read_tail(latest)
        snapshot = self._parse_rows(
            rows,
            sessions_today=0,
            active=latest.is_relative_to(self._sessions_root) and self._is_recently_updated(latest),
        )
        if snapshot.model == "Codex":
            model = self._model_cache.get(latest) or self._find_recent_model(latest)
            if model:
                self._model_cache[latest] = model
                snapshot = snapshot.model_copy(update={"model": model})
        else:
            self._model_cache[latest] = snapshot.model
        return self._apply_daily_usage(snapshot)

    def _refresh_daily_usage(self, files: list[Path]) -> None:
        """增量扫描所有 session 的逐次响应用量，避免把单个 rollout 当成每日总量。"""

        current_files = set(files)
        cache_invalid = not set(self._usage_offsets).issubset(current_files)
        if not cache_invalid:
            for path, offset in self._usage_offsets.items():
                try:
                    if path.stat().st_size < offset:
                        cache_invalid = True
                        break
                except OSError:
                    cache_invalid = True
                    break

        # 兼容：文件删除或截断后必须完整重建，否则旧贡献无法从累计值中安全扣除。
        if cache_invalid:
            self._usage_offsets.clear()
            self._daily_usage.clear()
            self._daily_sessions.clear()
            self._session_ids.clear()
            self._seen_usage.clear()
            self._last_usage_state.clear()
            self._daily_audit.clear()

        for path in files:
            self._scan_appended_usage(path)

        # 持久化：批量写入本轮新增事件；唯一指纹使进程重启后的全量扫描保持幂等。
        if self._history_repository is not None and self._pending_usage_events:
            self._history_repository.save_codex_usage(self._pending_usage_events)
            # 可靠性：只在事务成功后清空，短暂写入失败会在下一轮自动重试。
            self._pending_usage_events.clear()

        # 边界：仅保留当前展示需要的 31 天聚合，文件游标仍阻止重复计数。
        cutoff = datetime.now().astimezone().date() - timedelta(days=31)
        for day in tuple(self._daily_usage):
            if day < cutoff:
                self._daily_usage.pop(day, None)
                self._daily_sessions.pop(day, None)

    def _scan_appended_usage(self, path: Path) -> None:
        """从上次完整行结束位置继续读取，仅提取 token_count 数值字段。"""

        offset = self._usage_offsets.get(path, 0)
        try:
            size = path.stat().st_size
            if size <= offset:
                return
            with path.open("rb") as handle:
                handle.seek(offset)
                while True:
                    line_start = handle.tell()
                    raw = handle.readline()
                    if not raw:
                        break
                    complete_line = raw.endswith(b"\n")
                    try:
                        row = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        if not complete_line:
                            handle.seek(line_start)
                            break
                    else:
                        if isinstance(row, dict):
                            self._accumulate_usage(path, row)
                    offset = handle.tell()
        except OSError:
            # 兼容：Codex 正在轮换文件时本轮跳过，下一秒会从原游标继续。
            return
        self._usage_offsets[path] = offset

    def _accumulate_usage(self, path: Path, row: dict[str, Any]) -> None:
        """按事件本地日期累加 last_token_usage；每条记录代表一次实际响应。"""

        payload = row.get("payload")
        candidate_model = payload.get("model") if isinstance(payload, dict) else None
        if not candidate_model:
            candidate_model = row.get("model")
        if isinstance(candidate_model, str) and candidate_model:
            self._model_cache[path] = candidate_model
        candidate_cwd = payload.get("cwd") if isinstance(payload, dict) else None
        if not candidate_cwd:
            candidate_cwd = row.get("cwd")
        if isinstance(candidate_cwd, str) and candidate_cwd.strip():
            self._workspace_cache[path] = self._workspace_identity(candidate_cwd)
        if row.get("type") == "session_meta" and isinstance(payload, dict):
            if isinstance(payload.get("id"), str):
                self._session_ids[path] = payload["id"]
            return
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            return
        info = payload.get("info")
        if not isinstance(info, dict):
            return
        last_usage = info.get("last_token_usage") or info.get("last_usage")
        if not isinstance(last_usage, dict):
            return
        event_day = self._event_local_date(row)
        if event_day is None:
            return

        input_tokens = self._number(last_usage, "input_tokens")
        output_tokens = self._number(last_usage, "output_tokens")
        values = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": self._number(
                last_usage, "cached_input_tokens", "cached_tokens"
            ),
            "reasoning_tokens": self._number(
                last_usage, "reasoning_output_tokens", "reasoning_tokens"
            ),
            "total_tokens": self._number(last_usage, "total_tokens")
            or input_tokens + output_tokens,
        }
        if not any(values.values()):
            return

        # 去重：同一会话的事件重放只计一次；相同单次用量但累计值增加仍是新请求。
        # 没有累计字段时只去除同时间戳的完全重复记录，不猜测两次响应是否相同。
        session_id = self._session_ids.get(path, path.name)
        cumulative = info.get("total_token_usage") or info.get("total_usage")
        cumulative_input = self._number(cumulative, "input_tokens") if isinstance(cumulative, dict) else 0
        cumulative_output = self._number(cumulative, "output_tokens") if isinstance(cumulative, dict) else 0
        # 对账：Codex 桌面“Token 活动”与累计快照求和高度吻合；原值单独保存，不能替代响应增量。
        activity_tokens = (
            self._number(cumulative, "total_tokens") or cumulative_input + cumulative_output
            if isinstance(cumulative, dict)
            else 0
        )
        state = json.dumps([cumulative, last_usage], sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(
            json.dumps([session_id, row.get("timestamp"), state]).encode()
        ).hexdigest()
        audit = self._daily_audit.setdefault(event_day, {
            "raw_tokens": 0, "accepted_tokens": 0, "duplicate_tokens": 0, "duplicate_events": 0,
        })
        audit["raw_tokens"] += values["total_tokens"]
        duplicate = fingerprint in self._seen_usage or (
            isinstance(cumulative, dict) and bool(cumulative)
            and self._last_usage_state.get(session_id) == state
        )
        self._seen_usage.add(fingerprint)
        self._last_usage_state[session_id] = state
        if duplicate:
            audit["duplicate_events"] += 1
            audit["duplicate_tokens"] += values["total_tokens"]
            return
        audit["accepted_tokens"] += values["total_tokens"]

        totals = self._daily_usage.setdefault(
            event_day,
            {key: 0 for key in values},
        )
        for key, value in values.items():
            totals[key] += value
        self._daily_sessions.setdefault(event_day, set()).add(Path(session_id))

        event_time = self._event_datetime(row)
        if event_time is not None and self._history_repository is not None:
            # 隐私：账本只保存不可逆会话摘要与数值元数据，不保存文件路径或对话内容。
            anonymous_session = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
            workspace_id, workspace_label = self._workspace_cache.get(path, ("", ""))
            self._pending_usage_events.append(CodexUsageEvent(
                timestamp=event_time,
                event_id=fingerprint,
                session_id=anonymous_session,
                model=self._model_cache.get(path, ""),
                workspace_id=workspace_id,
                workspace_label=workspace_label,
                input_tokens=values["input_tokens"],
                output_tokens=values["output_tokens"],
                cached_tokens=values["cached_tokens"],
                reasoning_tokens=values["reasoning_tokens"],
                total_tokens=values["total_tokens"],
                activity_tokens=activity_tokens,
            ))

    def usage_audit(self, days: int = 30) -> dict[str, int]:
        """返回最近自然日的原始/去重后数值对账，不暴露会话正文或路径。"""

        today = datetime.now().astimezone().date()
        cutoff = today - timedelta(days=days - 1)
        keys = ("raw_tokens", "accepted_tokens", "duplicate_tokens", "duplicate_events")
        rows = list(self._daily_audit.items())
        return {key: sum(value[key] for day, value in rows if cutoff <= day <= today) for key in keys}

    def _apply_daily_usage(self, snapshot: ProviderSnapshot) -> ProviderSnapshot:
        """用跨 session 的本地日累计覆盖单个 rollout 累计，并保留最新上下文状态。"""

        today = datetime.now().astimezone().date()
        yesterday = today - timedelta(days=1)
        if self._history_repository is not None:
            summary = self._history_repository.get_codex_usage_summary()
            today_usage = summary.range_usage.get("24H", UsageBreakdown())
            model = snapshot.model
            if model in {"Codex", "No sessions yet", "Unavailable"} and summary.model:
                model = summary.model
            return snapshot.model_copy(update={
                "model": model,
                "total_tokens": today_usage.total_tokens,
                "input_tokens": today_usage.input_tokens,
                "output_tokens": today_usage.output_tokens,
                "cached_tokens": today_usage.cached_tokens,
                "reasoning_tokens": today_usage.reasoning_tokens,
                "sessions_today": today_usage.interactions,
                "previous_day_tokens": summary.previous_day_tokens,
                "tokens_7d": summary.range_usage.get("7D", UsageBreakdown()).total_tokens,
                "tokens_30d": summary.range_usage.get("30D", UsageBreakdown()).total_tokens,
                "range_usage": summary.range_usage,
                "detail": f"Today across {today_usage.interactions} local session"
                f"{'s' if today_usage.interactions != 1 else ''}",
            })

        totals = self._daily_usage.get(today, {})
        sessions_today = len(self._daily_sessions.get(today, set()))
        return snapshot.model_copy(
            update={
                "total_tokens": totals.get("total_tokens", 0),
                "input_tokens": totals.get("input_tokens", 0),
                "output_tokens": totals.get("output_tokens", 0),
                "cached_tokens": totals.get("cached_tokens", 0),
                "reasoning_tokens": totals.get("reasoning_tokens", 0),
                "sessions_today": sessions_today,
                "previous_day_tokens": self._daily_usage.get(yesterday, {}).get(
                    "total_tokens", 0
                ),
                # 口径：7D/30D 为包含今天在内的本地自然日合计，跨午夜不会回退。
                "tokens_7d": self._sum_recent_days(today, 7),
                "tokens_30d": self._sum_recent_days(today, 30),
                # 功能：明细页按所选自然日范围展示同口径的输入、输出、缓存和会话数。
                "range_usage": {
                    "24H": self._range_usage(today, 1),
                    "7D": self._range_usage(today, 7),
                    "30D": self._range_usage(today, 30),
                },
                "detail": f"Today across {sessions_today} local session"
                f"{'s' if sessions_today != 1 else ''}",
            }
        )

    def _range_usage(self, today: date, days: int) -> UsageBreakdown:
        """合并最近自然日的用量，并对跨日出现的同一会话只计一次。"""

        dates = [today - timedelta(days=offset) for offset in range(days)]
        totals = {
            key: sum(self._daily_usage.get(day, {}).get(key, 0) for day in dates)
            for key in (
                "total_tokens",
                "input_tokens",
                "output_tokens",
                "cached_tokens",
                "reasoning_tokens",
            )
        }
        sessions: set[Path] = set()
        for day in dates:
            sessions.update(self._daily_sessions.get(day, set()))
        return UsageBreakdown(
            **totals,
            interactions=len(sessions),
            exact_completions=len(sessions),
        )

    def _sum_recent_days(self, today: date, days: int) -> int:
        """汇总最近若干本地自然日的精确响应 token。"""

        return sum(
            self._daily_usage.get(today - timedelta(days=offset), {}).get(
                "total_tokens", 0
            )
            for offset in range(days)
        )

    def _is_recently_updated(self, path: Path) -> bool:
        """以 session 文件近期写入判断 Codex 是否正在运行，避免历史文件永久显示 active。"""

        try:
            return time.time() - path.stat().st_mtime <= self._active_window_seconds
        except OSError:
            return False

    @staticmethod
    def _event_local_date(row: dict[str, Any]) -> date | None:
        """把 JSONL 的 UTC 时间转换为系统本地日期，与用户看到的“今天”一致。"""

        parsed = CodexCollector._event_datetime(row)
        return parsed.astimezone().date() if parsed is not None else None

    @staticmethod
    def _event_datetime(row: dict[str, Any]) -> datetime | None:
        """解析事件时间并保留时区，供自然日聚合与 SQLite 账本共用。"""

        value = row.get("timestamp")
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone()

    @staticmethod
    def _workspace_identity(value: str) -> tuple[str, str]:
        """把完整工作区路径转换为稳定摘要与末级目录名，避免数据库泄露本机目录结构。"""

        trimmed = value.strip().rstrip("\\/")
        display_value = trimmed.replace("\\", "/")
        normalized = display_value.casefold()
        raw_label = display_value.rsplit("/", 1)[-1] if display_value else ""
        label = "".join(character for character in raw_label if character.isprintable())[:80]
        if not normalized:
            return "", ""
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24], label

    def _read_tail(self, path: Path) -> list[dict[str, Any]]:
        """只读取文件尾部，避免长会话导致每次刷新都扫描整个文件。"""

        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - self._tail_bytes))
            if size > self._tail_bytes:
                handle.readline()
            raw_lines = handle.readlines()

        rows: list[dict[str, Any]] = []
        for raw in raw_lines:
            try:
                value = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows

    def _find_recent_model(self, path: Path) -> str | None:
        """首次启动时向后定位最近模型字段，之后使用文件级缓存。

        长会话的 `turn_context` 可能落在常规尾读窗口之外。这里最多读取 32 MiB，
        只解析结构化行并立即丢弃内容字段；该慢路径每个 session 文件最多执行一次。
        """

        max_scan_bytes = 32 * 1024 * 1024
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_scan_bytes))
            if size > max_scan_bytes:
                handle.readline()
            raw_lines = handle.readlines()

        for raw in reversed(raw_lines):
            if b'"model"' not in raw:
                continue
            try:
                row = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            payload = row.get("payload")
            candidates = (payload, row)
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                model = candidate.get("model")
                if isinstance(model, str) and model:
                    return model
        return None

    def _parse_rows(
        self,
        rows: list[dict[str, Any]],
        sessions_today: int,
        active: bool = True,
    ) -> ProviderSnapshot:
        model = "Codex"
        total_usage: dict[str, Any] = {}
        last_usage: dict[str, Any] = {}
        context_size = 0

        for row in rows:
            payload = row.get("payload")
            if not isinstance(payload, dict):
                payload = row

            # 处理：模型可能出现在 turn_context 或 session_meta 中。
            candidate_model = payload.get("model") or row.get("model")
            if isinstance(candidate_model, str) and candidate_model:
                model = candidate_model

            payload_type = payload.get("type") or row.get("type")
            if payload_type != "token_count":
                continue

            info = payload.get("info") or payload
            if not isinstance(info, dict):
                continue
            candidate_total = info.get("total_token_usage") or info.get("total_usage")
            candidate_last = info.get("last_token_usage") or info.get("last_usage")
            if isinstance(candidate_total, dict):
                total_usage = candidate_total
            if isinstance(candidate_last, dict):
                last_usage = candidate_last
            candidate_window = info.get("model_context_window") or info.get(
                "context_window"
            )
            if isinstance(candidate_window, (int, float)):
                context_size = int(candidate_window)

        input_tokens = self._number(total_usage, "input_tokens")
        output_tokens = self._number(total_usage, "output_tokens")
        cached_tokens = self._number(
            total_usage, "cached_input_tokens", "cached_tokens"
        )
        reasoning_tokens = self._number(
            total_usage, "reasoning_output_tokens", "reasoning_tokens"
        )
        total_tokens = self._number(total_usage, "total_tokens") or (
            input_tokens + output_tokens
        )
        context_used = self._number(last_usage, "input_tokens")

        return ProviderSnapshot(
            provider="codex",
            online=True,
            status="active" if active and rows else "idle",
            model=model,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            context_used=context_used,
            context_size=context_size,
            sessions_today=sessions_today,
            detail="Local session metadata",
        )

    @staticmethod
    def _number(source: dict[str, Any], *keys: str) -> int:
        for key in keys:
            value = source.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        return 0
