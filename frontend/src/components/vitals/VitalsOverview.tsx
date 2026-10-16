import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { DashboardView, OverviewSnapshot, TimeRange, TokenActivityPoint, TrendPoint } from "../../types/dashboard";
import { formatCompact, formatDuration, formatPercent } from "../../utils/format";
import { getRangeTokenTotal, getRangeUsage } from "../../utils/tokens";
import { AntigravityIcon, CodeIcon, HardwareIcon, ModelIcon } from "../icons/Icons";
import { VitalsCard } from "./VitalsCard";
import { VitalsInspector } from "./VitalsInspector";
import { WorthALook } from "./WorthALook";

interface VitalsOverviewProps {
  snapshot: OverviewSnapshot;
  range: TimeRange;
  history: TrendPoint[];
  tokenActivity: TokenActivityPoint[];
  onNavigate: (view: DashboardView) => void;
}

export function VitalsOverview({
  snapshot,
  range,
  history,
  tokenActivity,
  onNavigate,
}: VitalsOverviewProps) {
  const { i18n } = useTranslation();
  const isZh = i18n.resolvedLanguage?.startsWith("zh") ?? false;

  // 默认选中总 Token 卡片 (TOKEN VOLUME)
  const [selectedCard, setSelectedCard] = useState<string>("volume");

  const ol = snapshot.ollama;
  const codex = snapshot.codex;
  const ag = snapshot.antigravity;
  const hw = snapshot.hardware;

  const olTotal = getRangeTokenTotal(ol, range);
  const codexTotal = getRangeTokenTotal(codex, range);
  const agTotal = getRangeTokenTotal(ag, range);
  const combTotal = olTotal + codexTotal + agTotal;

  const codexUsage = getRangeUsage(codex, range);
  const agUsage = getRangeUsage(ag, range);

  // 提取各指标的历史波形数据
  const ollamaSpark = history.map((p) => (p.ollama_tokens_per_second > 0 ? p.ollama_tokens_per_second : p.ollama_tokens));
  const codexSpark = history.map((p) => p.codex_tokens ?? 0);
  const agSpark = history.map((p) => p.antigravity_tokens ?? 0);
  const gpuSpark = history.map((p) => p.gpu_usage ?? 0);
  const ramSpark = history.map((p) => p.ram_usage ?? 0);
  const volumeSpark = history.map(
    (p) => (p.ollama_tokens ?? 0) + (p.codex_tokens ?? 0) + (p.antigravity_tokens ?? 0)
  );

  const isInferenceActive = ol.tokens_per_second > 0 || (ag.online && ag.status === "active");

  return (
    <div className="vitals-master-detail">
      {/* 左栏：2×3 六宫格核心指标卡 + Worth a Look 动态流 */}
      <section className="vitals-left-col">
        <div className="vitals-grid-6">
          {/* 1. Ollama 卡片 */}
          <VitalsCard
            cardKey="ollama"
            title="OLLAMA"
            icon={<ModelIcon />}
            subtitle={ol.model || (isZh ? "本地推理服务" : "Local Inference Engine")}
            figureValue={ol.tokens_per_second.toFixed(1)}
            figureUnit="T/s"
            statusState={ol.online ? (ol.tokens_per_second > 0 ? "active" : "idle") : "offline"}
            delta={ol.tokens_per_second > 0 ? { text: "LIVE", positive: true } : (ol.online ? { text: "READY" } : { text: "OFFLINE" })}
            sparklineUnit="T/s"
            stats={[
              { label: isZh ? "今日产出" : "Today", value: formatCompact(ol.total_tokens) },
              { label: isZh ? "状态" : "Status", value: ol.status.toUpperCase() },
              {
                label: isZh ? "上下文" : "Context",
                value: `${formatPercent(ol.context_used, ol.context_size).toFixed(0)}%`,
              },
            ]}
            sparklineValues={ollamaSpark}
            tintColor="var(--v-cyan)"
            isSelected={selectedCard === "ollama"}
            onClick={() => setSelectedCard("ollama")}
          />

          {/* 2. Codex 卡片 */}
          <VitalsCard
            cardKey="codex"
            title="CODEX"
            icon={<CodeIcon />}
            subtitle={codex.model || "gpt-4o"}
            figureValue={formatCompact(codexTotal)}
            figureUnit="Tokens"
            statusState={codex.online ? "active" : "idle"}
            delta={codexUsage.interactions > 0 ? { text: `${codexUsage.interactions} SESS`, positive: true } : { text: "STANDBY" }}
            sparklineUnit="Tokens"
            stats={[
              { label: isZh ? "输入" : "Input", value: formatCompact(codexUsage.input_tokens) },
              { label: isZh ? "输出" : "Output", value: formatCompact(codexUsage.output_tokens) },
              { label: isZh ? "缓存" : "Cached", value: formatCompact(codexUsage.cached_tokens) },
            ]}
            sparklineValues={codexSpark}
            tintColor="var(--v-purple)"
            isSelected={selectedCard === "codex"}
            onClick={() => setSelectedCard("codex")}
          />

          {/* 3. Antigravity 卡片 */}
          <VitalsCard
            cardKey="antigravity"
            title="ANTIGRAVITY"
            icon={<AntigravityIcon />}
            subtitle={ag.model || "Gemini 3.8"}
            figureValue={formatCompact(agTotal)}
            figureUnit="Tokens"
            statusState={ag.online ? "active" : "idle"}
            delta={
              agUsage.interactions > 0
                ? {
                    text: `${((agUsage.cached_tokens / Math.max(1, agUsage.input_tokens + agUsage.cached_tokens)) * 100).toFixed(0)}% CACHE`,
                    positive: true,
                  }
                : { text: "STANDBY" }
            }
            sparklineUnit="Tokens"
            stats={[
              { label: isZh ? "新输入" : "Input", value: formatCompact(agUsage.input_tokens) },
              { label: isZh ? "输出" : "Output", value: formatCompact(agUsage.output_tokens) },
              { label: isZh ? "缓存" : "Cached", value: formatCompact(agUsage.cached_tokens) },
            ]}
            sparklineValues={agSpark}
            tintColor="var(--v-amber)"
            isSelected={selectedCard === "antigravity"}
            onClick={() => setSelectedCard("antigravity")}
          />

          {/* 4. GPU 卡片 */}
          <VitalsCard
            cardKey="gpu"
            title="GPU ACCEL"
            icon={<HardwareIcon />}
            subtitle={hw.gpu_name || (isZh ? "独立显卡加速" : "Discrete GPU Acceleration")}
            figureValue={hw.gpu_usage}
            figureUnit="%"
            statusState={hw.gpu_available ? "active" : "offline"}
            delta={isInferenceActive ? { text: "⚡ AI ACTIVE", positive: true } : (hw.gpu_temperature_c !== null ? { text: `${hw.gpu_temperature_c}°C`, positive: hw.gpu_temperature_c < 75 } : { text: "READY" })}
            sparklineUnit="%"
            stats={[
              { label: isZh ? "显存占用" : "VRAM", value: `${hw.vram_used_gb.toFixed(1)}G` },
              { label: isZh ? "核心温度" : "Temp", value: hw.gpu_temperature_c !== null ? `${hw.gpu_temperature_c}°C` : "N/A" },
              { label: isZh ? "实时功耗" : "Power", value: hw.gpu_power_w !== null ? `${hw.gpu_power_w}W` : "N/A" },
            ]}
            sparklineValues={gpuSpark}
            tintColor="var(--v-pink)"
            isSelected={selectedCard === "gpu"}
            onClick={() => setSelectedCard("gpu")}
          />

          {/* 5. Host Memory & CPU 卡片 */}
          <VitalsCard
            cardKey="host"
            title="HOST MEMORY"
            icon={<HardwareIcon />}
            subtitle={`${hw.cpu_frequency_mhz} MHz · Uptime ${formatDuration(hw.uptime_seconds, isZh ? "zh" : "en")}`}
            figureValue={formatPercent(hw.ram_used_gb, hw.ram_total_gb).toFixed(0)}
            figureUnit="%"
            statusState="active"
            delta={{ text: `${hw.cpu_usage}% LOAD`, positive: hw.cpu_usage < 80 }}
            sparklineUnit="%"
            stats={[
              { label: isZh ? "物理内存" : "RAM", value: `${hw.ram_used_gb.toFixed(1)}G` },
              { label: isZh ? "CPU负载" : "CPU", value: `${hw.cpu_usage}%` },
              { label: isZh ? "总容量" : "Total", value: `${hw.ram_total_gb.toFixed(0)}G` },
            ]}
            sparklineValues={ramSpark}
            tintColor="var(--v-green)"
            isSelected={selectedCard === "host"}
            onClick={() => setSelectedCard("host")}
          />

          {/* 6. Total Token Volume 卡片 */}
          <VitalsCard
            cardKey="volume"
            title="TOKEN VOLUME"
            icon={
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 20V10M12 20V4M6 20v-6" />
              </svg>
            }
            subtitle={isZh ? "三端统一产出总量" : "All Providers Combined"}
            figureValue={formatCompact(combTotal)}
            figureUnit="Tokens"
            statusState="active"
            delta={{ text: "3 SOURCES", positive: true }}
            sparklineUnit="Tokens"
            stats={[
              { label: "Antigravity", value: formatCompact(agTotal) },
              { label: "Codex", value: formatCompact(codexTotal) },
              { label: "Ollama", value: formatCompact(olTotal) },
            ]}
            sparklineValues={volumeSpark}
            tintColor="var(--v-blue)"
            isSelected={selectedCard === "volume"}
            onClick={() => setSelectedCard("volume")}
          />
        </div>

        {/* Worth a Look 动态流，带分类过滤与点击联动 */}
        <WorthALook
          signals={snapshot.recent_signals}
          onShowAll={() => onNavigate("operations")}
          onSelectCard={(key) => setSelectedCard(key)}
        />
      </section>

      {/* 右栏：深度检视器 (Inspector) */}
      <VitalsInspector
        selectedKey={selectedCard}
        snapshot={snapshot}
        range={range}
        history={history}
        tokenActivity={tokenActivity}
        onNavigate={onNavigate}
      />
    </div>
  );
}
