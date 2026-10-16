import { useEffect, useState } from "react";
import type { OperationsData } from "../types/operations";

/** 功能：按筛选加载运营快照；首页定时更新，翻页锁定水位，旧查询不能覆盖新结果。 */
export function useOperations(query: string, live: boolean) {
  const [result, setResult] = useState<{ key: string; data?: OperationsData; error?: boolean }>();
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    async function load() {
      const timeout = new AbortController();
      const timeoutId = window.setTimeout(() => timeout.abort(), 10_000);
      try {
        const response = await fetch(`/api/analytics/operations?${query}`, {
          signal: AbortSignal.any([controller.signal, timeout.signal]),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data: OperationsData = await response.json();
        if (!controller.signal.aborted) setResult({ key: query, data });
      } catch {
        if (!controller.signal.aborted) setResult({ key: query, error: true });
      } finally {
        window.clearTimeout(timeoutId);
        // 处理：失败也重试；非首页使用相同水位，分页期间不插入新记录。
        if (!controller.signal.aborted) timer = window.setTimeout(() => void load(), live ? 5_000 : 30_000);
      }
    }
    void load();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query, live]);
  const current = result?.key === query ? result : undefined;
  return { data: current?.data, error: current?.error, loading: !current };
}
