import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ConnectionState, DashboardView, TimeRange } from "../../types/dashboard";
import {
  AnalyticsIcon,
  AntigravityIcon,
  CodeIcon,
  HardwareIcon,
  ModelIcon,
  OverviewIcon,
} from "../icons/Icons";

interface VitalsHeaderProps {
  currentView: DashboardView;
  connection: ConnectionState;
  range: TimeRange;
  onNavigate: (view: DashboardView) => void;
  onRangeChange: (range: TimeRange) => void;
}

function RealtimeClock({ locale }: { locale: string }) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <time className="clock-display" dateTime={now.toISOString()}>
      {now.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}
    </time>
  );
}

export function VitalsHeader({
  currentView,
  connection,
  range,
  onNavigate,
  onRangeChange,
}: VitalsHeaderProps) {
  const { t, i18n } = useTranslation();
  const isZh = i18n.resolvedLanguage?.startsWith("zh") ?? false;
  const currentLang = isZh ? "zh" : "en";

  const changeLanguage = (next: "zh" | "en") => {
    if (next !== currentLang) {
      void i18n.changeLanguage(next);
    }
  };

  const navItems: Array<{ id: DashboardView; label: string; icon: React.ReactNode }> = [
    { id: "overview", label: t("nav.overview"), icon: <OverviewIcon /> },
    { id: "operations", label: t("nav.operations"), icon: <AnalyticsIcon /> },
    { id: "ollama", label: "Ollama", icon: <ModelIcon /> },
    { id: "codex", label: "Codex", icon: <CodeIcon /> },
    { id: "antigravity", label: "Antigravity", icon: <AntigravityIcon /> },
    { id: "hardware", label: t("nav.hardware"), icon: <HardwareIcon /> },
  ];

  const ranges: TimeRange[] = ["24H", "7D", "30D"];
  const connectionLabel = connection === "live"
    ? "LIVE"
    : connection === "demo"
    ? "DEMO"
    : connection === "connecting"
    ? "SYNC"
    : "OFFLINE";

  // 滑动胶囊指示器
  const tabsNavRef = useRef<HTMLElement>(null);
  const [indicator, setIndicator] = useState<{ left: number; width: number; ready: boolean }>({
    left: 0,
    width: 0,
    ready: false,
  });

  useEffect(() => {
    const updateIndicator = () => {
      if (!tabsNavRef.current) return;
      const activeEl = tabsNavRef.current.querySelector<HTMLButtonElement>(".vitals-tab.is-active");
      if (activeEl) {
        setIndicator({
          left: activeEl.offsetLeft,
          width: activeEl.offsetWidth,
          ready: true,
        });
      }
    };
    updateIndicator();
    const id = requestAnimationFrame(updateIndicator);
    window.addEventListener("resize", updateIndicator);
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("resize", updateIndicator);
    };
  }, [currentView]);

  return (
    <header className="vitals-header" role="banner">
      {/* 左侧：品牌标题与副标题 */}
      <div className="vitals-header-left">
        <div className="brand-meta">
          <span className="brand-title">NEURODECK</span>
          <span className="brand-subtitle">
            {isZh ? "本地 AI 与系统遥测中心" : "Local AI & Machine Vitals"}
          </span>
        </div>
      </div>

      {/* 中间：全圆角胶囊分段导航标签（含平滑滑动高亮底色） */}
      <nav className="vitals-tabs" ref={tabsNavRef} aria-label={t("nav.primary")}>
        {indicator.ready && (
          <span
            className="vitals-tab-indicator"
            style={{
              transform: `translateX(${indicator.left}px)`,
              width: `${indicator.width}px`,
            }}
            aria-hidden="true"
          />
        )}
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`vitals-tab ${isActive ? "is-active" : ""}`}
              onClick={() => onNavigate(item.id)}
              aria-current={isActive ? "page" : undefined}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* 右侧：时钟、状态灯、时间范围切换与语言切换 */}
      <div className="vitals-header-right">
        <RealtimeClock locale={isZh ? "zh-CN" : "en-US"} />

        <div
          className="status-badge"
          title={`Connection status: ${connection}`}
          style={
            connection !== "live"
              ? {
                  borderColor: "rgba(239, 68, 68, 0.3)",
                  background: "rgba(239, 68, 68, 0.1)",
                  color: "#f87171",
                }
              : undefined
          }
        >
          <span
            className="status-badge-dot"
            style={connection !== "live" ? { background: "#ef4444", boxShadow: "0 0 6px #ef4444" } : undefined}
          />
          <span>{connectionLabel}</span>
        </div>

        <div className="range-picker" role="group" aria-label={t("topbar.trendRange")}>
          {ranges.map((r) => (
            <button
              key={r}
              type="button"
              className={`range-btn ${range === r ? "is-active" : ""}`}
              onClick={() => onRangeChange(r)}
            >
              {r}
            </button>
          ))}
        </div>

        <button
          type="button"
          className="lang-btn"
          onClick={() => changeLanguage(isZh ? "en" : "zh")}
          title={isZh ? "Switch to English" : "切换为中文"}
        >
          {isZh ? "中 / EN" : "EN / 中"}
        </button>
      </div>
    </header>
  );
}
