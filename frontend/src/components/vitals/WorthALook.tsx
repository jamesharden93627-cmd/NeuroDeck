import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SignalEvent } from "../../types/dashboard";

interface WorthALookProps {
  signals: SignalEvent[];
  onShowAll?: () => void;
  onSelectCard?: (cardKey: string) => void;
}

const signalEventKeys: Record<string, string> = {
  "TOKEN UPDATE": "signals.events.tokenUpdate",
  "INFERENCE COMPLETE": "signals.events.inferenceComplete",
  "MODEL LOADED": "signals.events.modelLoaded",
  "HIGH UTILIZATION": "signals.events.highUtilization",
  "THERMAL STABLE": "signals.events.thermalStable",
  "COLLECTORS READY": "signals.events.collectorsReady",
  "REQUEST COMPLETE": "signals.events.requestComplete",
};

function formatRelativeTime(timestamp: string, isZh: boolean): string {
  try {
    const diff = (Date.now() - new Date(timestamp).getTime()) / 1000;
    if (diff < 5) return isZh ? "刚刚" : "Just now";
    if (diff < 60) return isZh ? `${Math.floor(diff)}秒前` : `${Math.floor(diff)}s ago`;
    if (diff < 3600) return isZh ? `${Math.floor(diff / 60)}分钟前` : `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return isZh ? `${Math.floor(diff / 3600)}小时前` : `${Math.floor(diff / 3600)}h ago`;
    return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch {
    return timestamp;
  }
}

type CategoryType = "all" | "token" | "model" | "hardware" | "system";

function classifySignal(signal: SignalEvent): {
  tag: string;
  pillClass: string;
  category: CategoryType;
  targetCardKey: string;
} {
  const text = `${signal.source} ${signal.event} ${signal.detail}`.toLowerCase();
  if (text.includes("gpu")) {
    return { tag: "GPU", pillClass: "is-cpu", category: "hardware", targetCardKey: "gpu" };
  }
  if (text.includes("cpu") || text.includes("ram") || text.includes("utilization") || text.includes("thermal")) {
    return { tag: "Host", pillClass: "is-cpu", category: "hardware", targetCardKey: "host" };
  }
  if (text.includes("antigravity")) {
    return { tag: "Antigravity", pillClass: "is-token", category: "token", targetCardKey: "antigravity" };
  }
  if (text.includes("codex")) {
    return { tag: "Codex", pillClass: "is-token", category: "token", targetCardKey: "codex" };
  }
  if (text.includes("model") || text.includes("inference") || text.includes("ollama")) {
    return { tag: "Ollama", pillClass: "is-model", category: "model", targetCardKey: "ollama" };
  }
  if (text.includes("token")) {
    return { tag: "Token", pillClass: "is-token", category: "token", targetCardKey: "volume" };
  }
  return { tag: "System", pillClass: "is-storage", category: "system", targetCardKey: "volume" };
}

function getSignalIcon(pillClass: string) {
  switch (pillClass) {
    case "is-cpu":
      return (
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" />
        </svg>
      );
    case "is-model":
      return (
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z" />
          <path d="M12 6v6l4 2" />
        </svg>
      );
    case "is-token":
      return (
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m8 6-5 6 5 6M16 6l5 6-5 6M14 3l-4 18" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
        </svg>
      );
  }
}

export function WorthALook({ signals, onShowAll, onSelectCard }: WorthALookProps) {
  const { t, i18n } = useTranslation();
  const isZh = i18n.resolvedLanguage?.startsWith("zh") ?? false;
  const [filter, setFilter] = useState<CategoryType>("all");

  const translateEvent = (event: string) =>
    signalEventKeys[event] ? t(signalEventKeys[event]) : event;

  const translateDetail = (detail: string) =>
    isZh
      ? detail
          .replace(/\btokens?\b/gi, "Token")
          .replace(/\bsources active\b/gi, "个数据源活跃")
      : detail;

  // 分类统计数量
  const counts = {
    all: signals.length,
    token: signals.filter((s) => classifySignal(s).category === "token").length,
    model: signals.filter((s) => classifySignal(s).category === "model").length,
    hardware: signals.filter((s) => classifySignal(s).category === "hardware").length,
    system: signals.filter((s) => classifySignal(s).category === "system").length,
  };

  const filteredSignals = filter === "all"
    ? signals
    : signals.filter((s) => classifySignal(s).category === filter);

  // 截取最新的 6 条
  const displaySignals = filteredSignals.slice(0, 6);

  const filterTabs: Array<{ id: CategoryType; label: string }> = [
    { id: "all", label: isZh ? "全部" : "All" },
    { id: "token", label: "Token" },
    { id: "model", label: isZh ? "模型" : "Model" },
    { id: "hardware", label: isZh ? "硬件" : "Hardware" },
    { id: "system", label: isZh ? "系统" : "System" },
  ];

  return (
    <section className="worth-a-look" aria-label="Worth a look">
      <div className="worth-head">
        <h2 className="worth-title">
          {isZh ? "运行动态与热点事件" : "Worth a Look"}
        </h2>
        {signals.length > 5 && onShowAll && (
          <button type="button" className="worth-show-all" onClick={onShowAll}>
            {isZh ? `全部 ${signals.length} 条 →` : `All ${signals.length} events →`}
          </button>
        )}
      </div>

      {/* 分类快捷筛选胶囊 */}
      <div className="worth-filters" role="tablist">
        {filterTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`worth-filter-btn ${filter === tab.id ? "is-active" : ""}`}
            onClick={() => setFilter(tab.id)}
            role="tab"
            aria-selected={filter === tab.id}
          >
            <span>{tab.label}</span>
            <span className="worth-filter-count">{counts[tab.id]}</span>
          </button>
        ))}
      </div>

      <div className="worth-list">
        {displaySignals.length > 0 ? (
          displaySignals.map((sig, idx) => {
            const { tag, pillClass, targetCardKey } = classifySignal(sig);
            const relativeTime = formatRelativeTime(sig.timestamp, isZh);

            return (
              <div
                className={`worth-item ${onSelectCard ? "is-interactive" : ""}`}
                key={`${sig.timestamp}-${sig.event}-${idx}`}
                onClick={() => onSelectCard?.(targetCardKey)}
                role={onSelectCard ? "button" : undefined}
                tabIndex={onSelectCard ? 0 : undefined}
                title={onSelectCard ? (isZh ? `点击联动检视 ${tag}` : `Click to inspect ${tag}`) : undefined}
              >
                <div className="worth-icon">{getSignalIcon(pillClass)}</div>
                <div className="worth-copy">
                  <div className="worth-desc">{translateEvent(sig.event)}</div>
                  <div className="worth-detail" title={sig.detail}>
                    {sig.source} · {translateDetail(sig.detail)}
                  </div>
                </div>
                <div className="worth-meta">
                  <span className={`worth-pill ${pillClass}`}>{tag}</span>
                  <time className="worth-time" dateTime={sig.timestamp}>
                    {relativeTime}
                  </time>
                </div>
              </div>
            );
          })
        ) : (
          <div className="worth-item" style={{ justifyContent: "center", color: "var(--v-ink-3)" }}>
            <span>{isZh ? "该分类下暂无动态事件" : "No signals in this category"}</span>
          </div>
        )}
      </div>
    </section>
  );
}
