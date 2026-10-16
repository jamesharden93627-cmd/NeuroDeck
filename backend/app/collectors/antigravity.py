"""只读解析 Antigravity (Google Antigravity AI IDE) transcript JSONL。"""

from __future__ import annotations

import asyncio
import json
import hashlib
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.collectors.base import BaseCollector
from app.db.history import HistoryRepository
from app.schemas.dashboard import AntigravityUsageEvent, ProviderSnapshot, UsageBreakdown

# 匹配 antigravity_state.pbtxt 中的模型字段
_MODEL_RE = re.compile(r"last_selected_agent_model:\s+(\S+)")
_SETTINGS_MODEL_RE = re.compile(
    r"The user changed setting `Model Selection` from (?:.*?) to (.*?)\.(?:\s+No need|\n|</USER_SETTINGS_CHANGE>|$)"
)

KNOWN_MODELS: dict[str, str] = {
    "MODEL_PLACEHOLDER_M35": "Claude Sonnet 4.6 (Thinking)",
    "MODEL_PLACEHOLDER_M318": "Gemini 3.8",
    "Gemini 3.8 Flash (High)": "Gemini 3.8",
    "Gemini 3.8 Flash": "Gemini 3.8",
    "Gemini 3.8 Pro": "Gemini 3.8 Pro",
    "flash": "Gemini Flash",
    "flash_lite": "Gemini Flash Lite",
    "pro": "Gemini Pro",
}


def _humanize_model(raw: str) -> str:
    """把内部占位符转为可读显示名，例如 MODEL_PLACEHOLDER_M35 → Claude Sonnet 4.6 (Thinking)。

    已知映射直接转换，未知占位符取数字/后缀，保证始终有易读标签。
    """
    if not raw:
        return raw
    if raw in KNOWN_MODELS:
        return KNOWN_MODELS[raw]
    if "Gemini 3.8 Flash" in raw or raw.strip() == "Gemini 3.8":
        return "Gemini 3.8"
    # MODEL_PLACEHOLDER_Xxx → Xxx
    if raw.startswith("MODEL_PLACEHOLDER_"):
        return raw[len("MODEL_PLACEHOLDER_"):]
    # 其他含下划线形式取最后一节
    if "_" in raw:
        return raw.rsplit("_", 1)[-1]
    return raw


class AntigravityCollector(BaseCollector[ProviderSnapshot]):
    """读取 Antigravity transcript JSONL，只提取 token 数值，不读取对话正文。

    增量机制：维护每个 transcript.jsonl 的字节偏移，重启后全量扫描一次，
    之后只追读新增内容；SHA256 去重确保进程重启幂等。
    """

    def __init__(
        self,
        antigravity_home: Path,
        tail_bytes: int = 2_097_152,
        active_window_seconds: float = 30.0,
        history_repository: HistoryRepository | None = None,
    ) -> None:
        self._home = antigravity_home
        self._brain_root = antigravity_home / "brain"
        self._state_file = antigravity_home / "antigravity_state.pbtxt"
        self._tail_bytes = tail_bytes
        self._active_window_seconds = max(1.0, active_window_seconds)
        self._history_repository = history_repository

        # 增量读取游标：transcript 路径 → 已读字节偏移
        self._usage_offsets: dict[Path, int] = {}
        # 按自然日累计 token
        self._daily_usage: dict[date, dict[str, int]] = {}
        # 每日有 token 记录的会话集合
        self._daily_sessions: dict[date, set[str]] = {}
        # 去重：见过的事件指纹
        self._seen_usage: set[str] = set()
        # 对账数据
        self._daily_audit: dict[date, dict[str, int]] = {}
        # 待写数据库的事件
        self._pending_usage_events: list[AntigravityUsageEvent] = []
        # 当前模型缓存与按会话模型映射
        self._current_model: str = ""
        self._session_models: dict[str, str] = {}
        # 会话工作区元数据缓存：conv_id -> 目录 basename (如 NeuroDeck)
        self._summaries_db = antigravity_home / "conversation_summaries.db"
        self._workspace_labels: dict[str, str] = {}
        self._session_titles: dict[str, str] = {}

    def _load_summaries_metadata(self) -> None:
        """从 conversation_summaries.db 提取工作区目录名与标题；失败则安全回退。"""
        if not self._summaries_db.exists():
            return
        try:
            import sqlite3
            from urllib.parse import unquote, urlparse
            uri = f"file:{self._summaries_db.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=2.0) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT conversation_id, title, workspace_uris FROM conversation_summaries"
                ).fetchall()
                for row in rows:
                    cid = str(row["conversation_id"])
                    title = str(row["title"] or "")
                    if title:
                        self._session_titles[cid] = title
                    raw_uris = str(row["workspace_uris"] or "")
                    if raw_uris:
                        try:
                            uris = json.loads(raw_uris)
                            if uris and isinstance(uris, list) and isinstance(uris[0], str):
                                path = unquote(urlparse(uris[0]).path)
                                trimmed = path.strip().rstrip("\\/")
                                parts = [p for p in trimmed.replace("\\", "/").split("/") if p]
                                if parts:
                                    self._workspace_labels[cid] = parts[-1]
                        except Exception:
                            pass
        except Exception:
            pass

    async def collect(self) -> ProviderSnapshot:
        """在线程池中扫描 transcript，避免文件 I/O 阻塞事件循环。"""

        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> ProviderSnapshot:
        if not self._home.exists():
            return ProviderSnapshot(
                provider="antigravity",
                online=False,
                status="offline",
                detail="Antigravity home not found",
            )

        self._load_summaries_metadata()

        # 优先读取 IDE 实时选中的模型
        state_model = self._read_model_from_state()
        if state_model:
            self._current_model = state_model

        transcripts = self._find_transcripts()
        if not transcripts:
            return self._apply_daily_usage(
                ProviderSnapshot(
                    provider="antigravity",
                    online=True,
                    status="idle",
                    model=_humanize_model(self._current_model) or "Antigravity",
                    detail="Antigravity home detected, no sessions yet",
                )
            )

        self._refresh_daily_usage(transcripts)

        latest = max(transcripts, key=lambda p: p.stat().st_mtime)
        active = self._is_recently_updated(latest)
        latest_conv_id = (
            latest.parts[latest.parts.index("brain") + 1]
            if "brain" in latest.parts
            else latest.parent.parent.parent.name
        )

        # 优先使用 IDE 当前选中的模型，若无则回退到当前会话记录或历史缓存
        if state_model:
            model_name = _humanize_model(state_model)
        else:
            model_name = (
                self._session_models.get(latest_conv_id)
                or _humanize_model(self._current_model)
                or "Antigravity"
            )

        return self._apply_daily_usage(
            ProviderSnapshot(
                provider="antigravity",
                online=True,
                status="active" if active else "idle",
                model=model_name,
                detail="Local transcript metadata",
            )
        )

    def _find_transcripts(self) -> list[Path]:
        """递归枚举所有 brain/{conv_id}/.system_generated/logs/transcript.jsonl。"""

        if not self._brain_root.exists():
            return []
        # 容错：glob 失败时返回空列表
        try:
            return list(self._brain_root.glob("*/.system_generated/logs/transcript.jsonl"))
        except OSError:
            return []

    def _read_model_from_state(self) -> str:
        """从 antigravity_state.pbtxt 解析 last_selected_agent_model 字段。

        文件缺失或格式变化时静默返回空字符串，不崩溃。
        """
        try:
            text = self._state_file.read_text(encoding="utf-8", errors="ignore")
            match = _MODEL_RE.search(text)
            return match.group(1) if match else ""
        except OSError:
            return ""

    def _refresh_daily_usage(self, transcripts: list[Path]) -> None:
        """增量扫描所有 transcript，只读取新增行。"""

        current_files = set(transcripts)
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

        if cache_invalid:
            self._usage_offsets.clear()
            self._daily_usage.clear()
            self._daily_sessions.clear()
            self._seen_usage.clear()
            self._daily_audit.clear()

        for path in transcripts:
            self._scan_appended_usage(path)

        if self._history_repository is not None and self._pending_usage_events:
            self._history_repository.save_antigravity_usage(self._pending_usage_events)
            self._pending_usage_events.clear()

        cutoff = datetime.now().astimezone().date() - timedelta(days=31)
        for day in tuple(self._daily_usage):
            if day < cutoff:
                self._daily_usage.pop(day, None)
                self._daily_sessions.pop(day, None)

    def _scan_appended_usage(self, path: Path) -> None:
        """从上次位置追读，只提取 PLANNER_RESPONSE token 数值字段。"""

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
            return
        self._usage_offsets[path] = offset

    def _accumulate_usage(self, path: Path, row: dict[str, Any]) -> None:
        """从 transcript 行中提取模型变更与 PLANNER_RESPONSE token 数值。"""

        # conversation_id 取自路径（brain/{conv_id}/…）
        conv_id = path.parts[path.parts.index("brain") + 1] if "brain" in path.parts else path.parent.parent.parent.name

        # 检查是否包含用户设置的显式模型名称（如 Claude Sonnet 4.6 (Thinking), Gemini 3.8 Flash (High) 等）
        content = row.get("content")
        if isinstance(content, str) and "Model Selection" in content:
            m = _SETTINGS_MODEL_RE.search(content)
            if m:
                sel = m.group(1).strip().rstrip(".")
                if sel and sel.lower() != "none":
                    self._session_models[conv_id] = _humanize_model(sel)

        if row.get("type") != "PLANNER_RESPONSE" or row.get("source") != "MODEL":
            return

        input_tokens = self._number(row, "input_tokens")
        output_tokens = self._number(row, "output_tokens")
        cache_read_tokens = self._number(row, "cache_read_tokens")

        if input_tokens == 0 and output_tokens == 0 and cache_read_tokens == 0:
            return

        # 方案 A：全量模型上下文吞吐口径（新输入 + 输出 + 上下文缓存读取）
        total_tokens = input_tokens + output_tokens + cache_read_tokens

        event_day = self._event_local_date(row)
        if event_day is None:
            return

        # 去重：SHA256(conversation_id + step_index + tokens_json)
        step_index = row.get("step_index", "")
        tokens_json = json.dumps(
            {"i": input_tokens, "o": output_tokens, "c": cache_read_tokens},
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(
            f"{conv_id}:{step_index}:{tokens_json}".encode()
        ).hexdigest()

        audit = self._daily_audit.setdefault(
            event_day,
            {"raw_tokens": 0, "accepted_tokens": 0, "duplicate_tokens": 0, "duplicate_events": 0},
        )
        audit["raw_tokens"] += total_tokens

        if fingerprint in self._seen_usage:
            audit["duplicate_events"] += 1
            audit["duplicate_tokens"] += total_tokens
            return
        self._seen_usage.add(fingerprint)
        audit["accepted_tokens"] += total_tokens

        totals = self._daily_usage.setdefault(
            event_day,
            {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "total_tokens": 0},
        )
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["cached_tokens"] += cache_read_tokens
        totals["total_tokens"] += total_tokens
        self._daily_sessions.setdefault(event_day, set()).add(conv_id)

        event_time = self._event_datetime(row)
        if event_time is not None and self._history_repository is not None:
            # 隐私：只保存匿名会话摘要和数值，不保存路径或对话内容。
            anonymous_session = hashlib.sha256(conv_id.encode("utf-8")).hexdigest()[:24]
            model_display = self._session_models.get(conv_id) or _humanize_model(self._current_model)
            # workspace_label：优先取真实工作区目录名称，若无则回退到短 ID
            workspace_label = self._workspace_labels.get(conv_id) or (conv_id[:8] if conv_id else "Unassigned")
            self._pending_usage_events.append(
                AntigravityUsageEvent(
                    timestamp=event_time,
                    event_id=fingerprint,
                    session_id=anonymous_session,
                    model=model_display,
                    workspace_label=workspace_label,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cache_read_tokens,
                    total_tokens=total_tokens,
                )
            )

    def usage_audit(self, days: int = 30) -> dict[str, int]:
        """返回最近自然日的原始/去重后数值，供对账页展示。"""

        today = datetime.now().astimezone().date()
        cutoff = today - timedelta(days=days - 1)
        keys = ("raw_tokens", "accepted_tokens", "duplicate_tokens", "duplicate_events")
        rows = list(self._daily_audit.items())
        return {key: sum(value[key] for day, value in rows if cutoff <= day <= today) for key in keys}

    def _apply_daily_usage(self, snapshot: ProviderSnapshot) -> ProviderSnapshot:
        """把跨会话的本地日累计写入快照。"""

        today = datetime.now().astimezone().date()
        yesterday = today - timedelta(days=1)

        if self._history_repository is not None:
            summary = self._history_repository.get_antigravity_usage_summary()
            today_usage = summary.range_usage.get("24H", UsageBreakdown())
            model = snapshot.model
            if model in {"Antigravity", "Unavailable", ""} and summary.model:
                model = summary.model
            return snapshot.model_copy(
                update={
                    "model": model,
                    "total_tokens": today_usage.total_tokens,
                    "input_tokens": today_usage.input_tokens,
                    "output_tokens": today_usage.output_tokens,
                    "cached_tokens": today_usage.cached_tokens,
                    "sessions_today": today_usage.interactions,
                    "previous_day_tokens": summary.previous_day_tokens,
                    "tokens_7d": summary.range_usage.get("7D", UsageBreakdown()).total_tokens,
                    "tokens_30d": summary.range_usage.get("30D", UsageBreakdown()).total_tokens,
                    "range_usage": summary.range_usage,
                    "detail": (
                        f"Today across {today_usage.interactions} local session"
                        f"{'s' if today_usage.interactions != 1 else ''}"
                    ),
                }
            )

        totals = self._daily_usage.get(today, {})
        sessions_today = len(self._daily_sessions.get(today, set()))
        return snapshot.model_copy(
            update={
                "total_tokens": totals.get("total_tokens", 0),
                "input_tokens": totals.get("input_tokens", 0),
                "output_tokens": totals.get("output_tokens", 0),
                "cached_tokens": totals.get("cached_tokens", 0),
                "sessions_today": sessions_today,
                "previous_day_tokens": self._daily_usage.get(yesterday, {}).get("total_tokens", 0),
                "tokens_7d": self._sum_recent_days(today, 7),
                "tokens_30d": self._sum_recent_days(today, 30),
                "range_usage": {
                    "24H": self._range_usage(today, 1),
                    "7D": self._range_usage(today, 7),
                    "30D": self._range_usage(today, 30),
                },
                "detail": (
                    f"Today across {sessions_today} local session"
                    f"{'s' if sessions_today != 1 else ''}"
                ),
            }
        )

    def _range_usage(self, today: date, days: int) -> UsageBreakdown:
        dates = [today - timedelta(days=offset) for offset in range(days)]
        totals = {
            key: sum(self._daily_usage.get(day, {}).get(key, 0) for day in dates)
            for key in ("total_tokens", "input_tokens", "output_tokens", "cached_tokens")
        }
        sessions: set[str] = set()
        for day in dates:
            sessions.update(self._daily_sessions.get(day, set()))
        return UsageBreakdown(
            **totals,
            reasoning_tokens=0,
            interactions=len(sessions),
            exact_completions=len(sessions),
        )

    def _sum_recent_days(self, today: date, days: int) -> int:
        return sum(
            self._daily_usage.get(today - timedelta(days=offset), {}).get("total_tokens", 0)
            for offset in range(days)
        )

    def _is_recently_updated(self, path: Path) -> bool:
        try:
            return time.time() - path.stat().st_mtime <= self._active_window_seconds
        except OSError:
            return False

    @staticmethod
    def _event_local_date(row: dict[str, Any]) -> date | None:
        parsed = AntigravityCollector._event_datetime(row)
        return parsed.astimezone().date() if parsed is not None else None

    @staticmethod
    def _event_datetime(row: dict[str, Any]) -> datetime | None:
        value = row.get("created_at")
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone()

    @staticmethod
    def _number(source: dict[str, Any], *keys: str) -> int:
        for key in keys:
            value = source.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        return 0
