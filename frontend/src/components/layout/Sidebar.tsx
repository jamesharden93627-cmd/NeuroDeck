import { AnalyticsIcon, AntigravityIcon, CodeIcon, HardwareIcon, ModelIcon, OverviewIcon } from "../icons/Icons";
import type { ConnectionState, DashboardView } from "../../types/dashboard";
import { useTranslation } from "react-i18next";
import { useRuntimeHealth } from "../../hooks/useRuntimeHealth";

const navigation = [
  { id: "overview", icon: OverviewIcon },
  { id: "operations", icon: AnalyticsIcon },
  { id: "ollama", icon: ModelIcon },
  { id: "codex", icon: CodeIcon },
  { id: "antigravity", icon: AntigravityIcon },
  { id: "hardware", icon: HardwareIcon },
] satisfies Array<{ id: DashboardView; icon: typeof OverviewIcon }>;

interface SidebarProps {
  activeView: DashboardView;
  connection: ConnectionState;
  onNavigate: (view: DashboardView) => void;
}

/** 功能：监控与请求分析共享导航，桌面侧栏与移动底栏保持相同语义。 */
export function Sidebar({ activeView, connection, onNavigate }: SidebarProps) {
  const { t } = useTranslation();
  const health = useRuntimeHealth();
  const runtimeOnline = connection === "live" && health?.status === "ok";
  const healthRows = [
    [t("nav.apiServer"), health?.api ?? "unknown"],
    [t("nav.collector"), health?.collector ?? "unknown"],
    [t("nav.storage"), health?.storage ?? "unknown"],
  ];
  const websocketLabel = connection === "live"
    ? t("common.healthy")
    : t(`common.${connection}`, { defaultValue: connection });

  return (
    <aside className="sidebar" aria-label={t("nav.primary")}>
      <div className="brand-block">
        <span className="brand-mark" aria-hidden="true">ND</span>
        <span className="brand-name">NEURODECK</span>
      </div>
      <nav className="nav-list">
        <span className="nav-section-label">{t("nav.monitoring")}</span>
        {navigation.map(({ id, icon: Icon }) => {
          const active = activeView === id;
          const label = t(`nav.${id}`);
          return (
            <button
              key={id}
              className={`nav-item${active ? " is-active" : ""}`}
              type="button"
              aria-current={active ? "page" : undefined}
              title={label}
              onClick={() => onNavigate(id)}
            >
              <Icon className="nav-icon" />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        <section className="runtime-card" aria-label={t("nav.runtimeStatus")}>
          <div className="runtime-heading">
            <span>{t("nav.runtime")}</span>
            <span className={`status-dot${runtimeOnline ? "" : " is-offline"}`} />
          </div>
          {healthRows.map(([label, state]) => <div key={label}><span>{label}</span><strong className={state === "healthy" ? "" : "is-offline"}>{t(`common.${state}`)}</strong></div>)}
          <div><span>{t("nav.websocket")}</span><strong className={connection === "live" ? "" : "is-offline"}>{websocketLabel}</strong></div>
        </section>
        <div className="sidebar-version"><span>{t("nav.localOnly")}</span><small>v0.3.0</small></div>
      </div>
    </aside>
  );
}
