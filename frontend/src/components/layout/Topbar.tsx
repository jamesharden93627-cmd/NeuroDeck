import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ConnectionState, DashboardView, TimeRange } from "../../types/dashboard";

const ranges: TimeRange[] = ["24H", "7D", "30D"];

function Clock({ locale }: { locale: string }) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  return <time>{now.toLocaleTimeString(locale, { hour12: false })}</time>;
}

interface TopbarProps {
  connection: ConnectionState;
  range: TimeRange;
  onRangeChange: (range: TimeRange) => void;
  section: DashboardView;
}

export function Topbar({ connection, range, onRangeChange, section }: TopbarProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage?.startsWith("zh") ? "zh" : "en";
  const label = t(`common.${connection}`, { defaultValue: connection.toUpperCase() });
  const sectionLabel = t(`nav.${section}`);

  /** 处理：语言变更由 i18next 广播，并在初始化模块中持久化到 localStorage。 */
  const changeLanguage = (nextLanguage: "zh" | "en") => {
    if (nextLanguage !== language) void i18n.changeLanguage(nextLanguage);
  };

  return (
    <header className="topbar">
      <div className="title-lockup">
        <span>{t("topbar.monitor")}</span>
        <i aria-hidden="true">/</i>
        <strong>{sectionLabel}</strong>
      </div>
      <div className="topbar-controls">
        <Clock locale={language === "zh" ? "zh-CN" : "en-US"} />
        <span className={`connection-state state-${connection}`}>
          <span className="status-dot" />
          {label}
        </span>
        <div className="range-control" aria-label={t("topbar.trendRange")}>
          {ranges.map((item) => (
            <button
              key={item}
              type="button"
              className={range === item ? "is-selected" : ""}
              aria-pressed={range === item}
              onClick={() => onRangeChange(item)}
            >
              {item === "24H" ? t("common.today") : item}
            </button>
          ))}
        </div>
        <div className="language-control" role="group" aria-label={t("topbar.language")}>
          <button
            type="button"
            className={language === "zh" ? "is-selected" : ""}
            aria-pressed={language === "zh"}
            aria-label={t("topbar.switchTo", { language: t("topbar.chinese") })}
            onClick={() => changeLanguage("zh")}
          >
            中
          </button>
          <button
            type="button"
            className={language === "en" ? "is-selected" : ""}
            aria-pressed={language === "en"}
            aria-label={t("topbar.switchTo", { language: t("topbar.english") })}
            onClick={() => changeLanguage("en")}
          >
            EN
          </button>
        </div>
      </div>
    </header>
  );
}
