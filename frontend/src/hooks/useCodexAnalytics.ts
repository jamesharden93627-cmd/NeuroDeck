import { useEffect, useState } from "react";

import { fetchCodexAnalytics } from "../api/dashboard";
import type { CodexAnalyticsResponse } from "../types/codexAnalytics";
import type { TimeRange } from "../types/dashboard";

interface CodexAnalyticsState {
  data: CodexAnalyticsResponse | null;
  loading: boolean;
  error: boolean;
}

interface InternalCodexAnalyticsState extends CodexAnalyticsState {
  loadedRange: TimeRange | null;
}

/** 功能：仅在 Codex 详情页挂载时轮询分析，避免总览页面加载不需要的数据。 */
export function useCodexAnalytics(range: TimeRange): CodexAnalyticsState {
  const [state, setState] = useState<InternalCodexAnalyticsState>({
    data: null,
    loading: true,
    error: false,
    loadedRange: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;

    const load = () => {
      if (inFlight) return;
      inFlight = true;
      void fetchCodexAnalytics(range, controller.signal)
        .then((data) => {
          if (!controller.signal.aborted) {
            setState({ data, loading: false, error: false, loadedRange: range });
          }
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
          setState({ data: null, loading: false, error: true, loadedRange: range });
        })
        .finally(() => { inFlight = false; });
    };

    load();
    const refreshTimer = window.setInterval(load, 5_000);
    return () => {
      controller.abort();
      window.clearInterval(refreshTimer);
    };
  }, [range]);

  // 处理：时间范围切换期间隐藏旧范围数据，等待异步响应后再原子替换。
  if (state.loadedRange !== range) {
    return { data: null, loading: true, error: false };
  }
  return { data: state.data, loading: state.loading, error: state.error };
}
