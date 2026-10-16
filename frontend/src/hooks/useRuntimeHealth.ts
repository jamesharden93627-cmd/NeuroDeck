import { useEffect, useState } from "react";

interface RuntimeHealth {
  status: string;
  api: string;
  collector: string;
  storage: string;
}

/** 功能：独立探测 API、采集器和存储，不能根据 WebSocket/Demo 推测组件健康。 */
export function useRuntimeHealth(): RuntimeHealth | null {
  const [health, setHealth] = useState<RuntimeHealth | null>(null);
  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;
    let controller: AbortController;
    const poll = async () => {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 4_000);
      try {
        const response = await fetch("/api/health", { signal: controller.signal });
        const value = await response.json() as Partial<RuntimeHealth>;
        if (!response.ok || !value.api || !value.collector || !value.storage) throw new Error("Invalid health response");
        if (!disposed) setHealth(value as RuntimeHealth);
      } catch {
        if (!disposed) setHealth({ status: "degraded", api: "offline", collector: "unknown", storage: "unknown" });
      } finally {
        window.clearTimeout(timeout);
        if (!disposed) timer = window.setTimeout(() => void poll(), 5_000);
      }
    };
    void poll();
    return () => { disposed = true; controller?.abort(); window.clearTimeout(timer); };
  }, []);
  return health;
}
