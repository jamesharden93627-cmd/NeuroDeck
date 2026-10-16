import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AntigravityDetail, CodexDetail, HardwareDetail, OllamaDetail } from "./components/details/DetailViews";
import { OperationsView } from "./components/operations/OperationsView";
import { VitalsHeader } from "./components/vitals/VitalsHeader";
import { VitalsOverview } from "./components/vitals/VitalsOverview";
import { useDashboard } from "./hooks/useDashboard";
import type { DashboardView, TimeRange } from "./types/dashboard";

export function App() {
  const { t } = useTranslation();
  const [range, setRange] = useState<TimeRange>("24H");
  const [view, setView] = useState<DashboardView>("overview");
  const {
    snapshot,
    connection,
    history,
    historyLoading,
    historyError,
    tokenActivity,
    activityLoading,
    activityError,
  } = useDashboard(range);

  const detailProps = { snapshot, history, tokenActivity, range, historyLoading, activityLoading, onNavigate: setView };

  return (
    <div className="vitals-app">
      <VitalsHeader
        currentView={view}
        connection={connection}
        range={range}
        onNavigate={setView}
        onRangeChange={setRange}
      />

      <main className="vitals-main">
        {historyError ? <div className="data-warning" role="status">{t("common.historyError")}</div> : null}
        {activityError ? <div className="data-warning" role="status">{t("common.activityError")}</div> : null}
        {connection === "offline" ? (
          <div className="data-warning" role="status">
            {t(snapshot.mode === "waiting" ? "common.awaitingData" : "common.staleData")}
          </div>
        ) : null}

        {snapshot.mode === "waiting" && view !== "operations" ? (
          <div className="detail-center" role="status">{t("common.awaitingData")}</div>
        ) : view === "overview" ? (
          <div key="overview" className="vitals-view-anim">
            <VitalsOverview
              snapshot={snapshot}
              range={range}
              history={history}
              tokenActivity={tokenActivity}
              onNavigate={setView}
            />
          </div>
        ) : view === "operations" ? (
          <div key="operations" className="vitals-subview-wrapper vitals-view-anim">
            <OperationsView key={range} range={range} onNavigate={setView} />
          </div>
        ) : (
          <div key={view} className={`detail-center detail-center-${view} vitals-subview-wrapper vitals-view-anim`}>
            {view === "ollama" ? <OllamaDetail {...detailProps} /> : null}
            {view === "codex" ? <CodexDetail {...detailProps} /> : null}
            {view === "antigravity" ? <AntigravityDetail {...detailProps} /> : null}
            {view === "hardware" ? <HardwareDetail {...detailProps} /> : null}
          </div>
        )}
      </main>
    </div>
  );
}
