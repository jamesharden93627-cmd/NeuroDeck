import { useEffect, useRef, useState } from "react";

import { fetchHistory, fetchOverview, fetchTokenActivity, realtimeUrl } from "../api/dashboard";
import { emptySnapshot } from "../data/empty";
import type { ConnectionState, OverviewSnapshot, RealtimeUpdate, TimeRange, TokenActivityPoint, TokenVolumeBucket, TrendPoint } from "../types/dashboard";
import { activityToTokenVolume } from "../utils/tokenVolume";

interface DashboardStore {
  snapshot: OverviewSnapshot;
  connection: ConnectionState;
  history: TrendPoint[];
  loadedRange: TimeRange | null;
  historyError: boolean;
  tokenActivity: TokenActivityPoint[];
  loadedActivityRange: TimeRange | null;
  activityError: boolean;
  tokenVolume: TokenVolumeBucket[];
  loadedVolumeRange: TimeRange | null;
  volumeError: boolean;
}

interface DashboardState extends Omit<DashboardStore, "loadedRange" | "loadedActivityRange" | "loadedVolumeRange"> {
  historyLoading: boolean;
  activityLoading: boolean;
  volumeLoading: boolean;
}

const initialState: DashboardStore = {
  snapshot: emptySnapshot,
  connection: "connecting",
  history: [],
  loadedRange: null,
  historyError: false,
  tokenActivity: [],
  loadedActivityRange: null,
  activityError: false,
  tokenVolume: [],
  loadedVolumeRange: null,
  volumeError: false,
};

const RANGE_BUCKET_MS: Record<TimeRange, number> = {
  "24H": 5 * 60_000,
  "7D": 30 * 60_000,
  "30D": 2 * 60 * 60_000,
};

/**
 * 处理：将一秒实时点合并到当前时间桶，而不是持续追加导致长开页面无限增长。
 * 历史 API 与这里共享同一桶宽，因此切换范围后曲线密度保持稳定。
 */
function mergeRealtimePoint(
  history: TrendPoint[],
  point: TrendPoint | undefined,
  range: TimeRange,
): TrendPoint[] {
  if (!point) return history;
  if (history.length === 0) return [point];

  const bucketSize = RANGE_BUCKET_MS[range];
  const pointBucket = Math.floor(new Date(point.timestamp).getTime() / bucketSize);
  const lastBucket = Math.floor(
    new Date(history[history.length - 1].timestamp).getTime() / bucketSize,
  );
  if (pointBucket === lastBucket) {
    return [...history.slice(0, -1), point];
  }
  return [...history, point].slice(-400);
}

/** 功能：验证 WebSocket 增量帧的最小结构，异常消息不会进入 React 状态。 */
function isRealtimeUpdate(value: unknown): value is RealtimeUpdate {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<RealtimeUpdate>;
  return candidate.type === "realtime_update"
    && typeof candidate.timestamp === "string"
    && Boolean(candidate.ollama)
    && Boolean(candidate.codex)
    && Boolean(candidate.hardware)
    && Array.isArray(candidate.recent_signals);
}

/**
 * 功能：先通过 REST 获取完整快照，再用 WebSocket 接收增量时刻的完整状态。
 * 断线时保留最后一帧；首次连接失败保持等待状态，不自动填入演示统计。
 */
export function useDashboard(range: TimeRange): DashboardState {
  const [state, setState] = useState<DashboardStore>(initialState);
  const rangeRef = useRef(range);
  const [reconnectEpoch, setReconnectEpoch] = useState(0);
  const dayBoundary = state.snapshot.range_starts?.["24H"];

  useEffect(() => {
    rangeRef.current = range;
    const controller = new AbortController();
    let retryTimer: number | undefined;

    // 恢复：切换范围、重连和本地换日时重新拉取历史；失败不冒充新范围已加载。
    const loadHistory = () => void fetchHistory(range, controller.signal)
      .then((history) => {
        if (controller.signal.aborted) return;
        setState((current) => ({ ...current, history, loadedRange: range, historyError: false }));
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
        setState((current) => ({ ...current, history: [], loadedRange: range, historyError: true }));
        retryTimer = window.setTimeout(loadHistory, 5_000);
      });
    loadHistory();

    return () => { controller.abort(); window.clearTimeout(retryTimer); };
  }, [range, reconnectEpoch, dayBoundary]);

  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;

    // 实时性：账本累计曲线按固定节流刷新，避免把硬件采样点误当成 Token 历史。
    const loadActivity = () => {
      if (inFlight) return;
      inFlight = true;
      void fetchTokenActivity(range, controller.signal)
        .then((tokenActivity) => {
          if (controller.signal.aborted) return;
          setState((current) => ({
            ...current,
            tokenActivity,
            loadedActivityRange: range,
            activityError: false,
            tokenVolume: activityToTokenVolume(tokenActivity, range),
            loadedVolumeRange: range,
            volumeError: false,
          }));
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
          setState((current) => ({
            ...current,
            tokenActivity: [],
            loadedActivityRange: range,
            activityError: true,
            tokenVolume: [],
            loadedVolumeRange: range,
            volumeError: true,
          }));
        })
        .finally(() => { inFlight = false; });
    };
    loadActivity();
    const refreshTimer = window.setInterval(loadActivity, 5_000);

    return () => {
      controller.abort();
      window.clearInterval(refreshTimer);
    };
  }, [range, reconnectEpoch, dayBoundary]);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let hasLiveData = false;
    let lastMessageAt = Date.now();

    const connectRealtime = () => {
      socket = new WebSocket(realtimeUrl());
      socket.addEventListener("open", () => {
        if (!disposed) {
          lastMessageAt = Date.now();
          setReconnectEpoch((current) => current + 1);
        }
      });
      socket.addEventListener("message", (event) => {
        if (disposed) return;
        try {
          const payload = JSON.parse(event.data as string) as unknown;
          if (isRealtimeUpdate(payload)) {
            hasLiveData = true;
            lastMessageAt = Date.now();
            setState((current) => {
              const history = current.loadedRange === rangeRef.current && !current.historyError ? mergeRealtimePoint(
                current.history,
                payload.history_point ?? undefined,
                rangeRef.current,
              ) : current.history;
              const overviewHistory = mergeRealtimePoint(
                current.snapshot.history,
                payload.history_point ?? undefined,
                "24H",
              );
              return {
                ...current,
                snapshot: {
                  timestamp: payload.timestamp,
                  mode: payload.mode,
                  range_starts: payload.range_starts,
                  ollama: payload.ollama,
                  codex: payload.codex,
                  antigravity: payload.antigravity,
                  codex_accounting: payload.codex_accounting,
                  antigravity_accounting: payload.antigravity_accounting,
                  hardware: payload.hardware,
                  history: overviewHistory,
                  recent_signals: payload.recent_signals,
                },
                connection: "live",
                history,
              };
            });
            return;
          }

          // 兼容：旧后端仍可能发送完整 OverviewSnapshot，升级过程不会中断页面。
          const snapshot = payload as OverviewSnapshot;
          if (!Array.isArray(snapshot.history) || !snapshot.ollama || !snapshot.codex) return;
          hasLiveData = true;
          lastMessageAt = Date.now();
          setState((current) => ({
            ...current,
            snapshot,
            connection: "live",
            history: mergeRealtimePoint(
              current.history,
              snapshot.history.at(-1),
              rangeRef.current,
            ),
          }));
        } catch {
          // 数据格式异常时保留最后一帧，等待下一次有效推送。
        }
      });
      socket.addEventListener("close", () => {
        if (disposed) return;
        setState((current) => ({
          ...current,
          connection: "offline",
        }));
        reconnectTimer = window.setTimeout(connectRealtime, 3_000);
      });
      socket.addEventListener("error", () => socket?.close());
    };

    // 并行准备 REST 首帧和实时连接，缩短页面进入 live 状态的等待时间。
    void fetchOverview(controller.signal)
      .then((snapshot) => {
        if (disposed) return;
        hasLiveData = true;
        setState((current) => current.connection === "live" && current.snapshot.timestamp > snapshot.timestamp
          ? current : { ...current, snapshot, connection: "live" });
      })
      .catch(() => {
        if (!disposed && !hasLiveData) {
          setState((current) => ({
            ...current,
            connection: "offline",
          }));
        }
      });
    connectRealtime();
    // 防假在线：有连接却长期无新帧时主动重连，让 UI 明确标记旧数据。
    const staleTimer = window.setInterval(() => {
      if (!disposed && hasLiveData && Date.now() - lastMessageAt > 15_000) {
        setState((current) => ({ ...current, connection: "offline" }));
        socket?.close();
      }
    }, 5_000);

    return () => {
      disposed = true;
      controller.abort();
      window.clearInterval(staleTimer);
      socket?.close();
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
    };
  }, []);

  const { loadedRange, loadedActivityRange, loadedVolumeRange, ...dashboard } = state;
  return {
    ...dashboard,
    history: loadedRange === range ? dashboard.history : [],
    tokenActivity: loadedActivityRange === range ? dashboard.tokenActivity : [],
    tokenVolume: loadedVolumeRange === range ? dashboard.tokenVolume : [],
    historyLoading: loadedRange !== range,
    activityLoading: loadedActivityRange !== range,
    volumeLoading: loadedVolumeRange !== range,
  };
}
