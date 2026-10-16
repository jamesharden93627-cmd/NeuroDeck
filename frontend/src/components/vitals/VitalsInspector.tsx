import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useCodexAnalytics } from "../../hooks/useCodexAnalytics";
import type { DashboardView, OverviewSnapshot, TimeRange, TokenActivityPoint, TrendPoint } from "../../types/dashboard";
import { formatCompact, formatDuration, formatPercent } from "../../utils/format";
import { getRangeTokenTotal, getRangeUsage } from "../../utils/tokens";
import { AntigravityIcon, CodeIcon, HardwareIcon, ModelIcon } from "../icons/Icons";

interface VitalsInspectorProps {
  selectedKey: "antigravity" | "codex" | "ollama" | "gpu" | "host" | "volume" | string;
  snapshot: OverviewSnapshot;
  range: TimeRange;
  history: TrendPoint[];
  tokenActivity?: TokenActivityPoint[];
  onNavigate: (view: DashboardView) => void;
}

interface SegmentSlice {
  label: string;
  amount: number;
  formattedAmount: string;
  percent: number;
  color: string;
}

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

export function VitalsInspector({
  selectedKey,
  snapshot,
  range,
  history,
  onNavigate,
}: VitalsInspectorProps) {
  const { i18n } = useTranslation();
  const isZh = i18n.resolvedLanguage?.startsWith("zh") ?? false;
  const chartGradId = useId().replace(/:/g, "_");

  // 轮询查询 Codex 详细会话数据（用于 Codex 检视）
  const { data: codexData } = useCodexAnalytics(range);

  // 波形图悬停交互状态
  const chartSvgRef = useRef<SVGSVGElement | null>(null);
  const [hoverChartIndex, setHoverChartIndex] = useState<number | null>(null);

  // 根据选中的 key 提取当前检视对象的元数据与度量
  let title = "";
  let subtitle = "";
  let icon = <ModelIcon />;
  let tintColor = "var(--v-cyan)";
  let targetView: DashboardView = "overview";
  let targetAction = isZh ? "进入深度分析" : "View Deep Analysis";

  interface StatTile {
    label: string;
    value: string;
    sub: string;
  }
  let stats: [StatTile, StatTile, StatTile, StatTile];
  let breakdownTitle = isZh ? "Token 构成分布" : "Token Breakdown";
  let breakdownTotalStr = "";
  let slices: SegmentSlice[] = [];
  let waveformValues: number[] = [];

  // 会话与流水数据
  let sessionHeadTitle = isZh ? "近期活跃会话" : "Active Sessions";
  let sessionCountStr = "";

  if (selectedKey === "antigravity") {
    tintColor = "var(--v-amber)";
    targetView = "antigravity";
    const ag = snapshot.antigravity;
    const total = getRangeTokenTotal(ag, range);
    const usage = getRangeUsage(ag, range);
    const isOnline = ag.online;

    title = isZh ? "Google Antigravity" : "Google Antigravity";
    subtitle = `${ag.model || "M35"} · ${isOnline ? (isZh ? "活跃监控中" : "Active") : (isZh ? "待命" : "Idle")}`;
    icon = <AntigravityIcon style={{ color: "#f59e0b" }} />;
    targetAction = isZh ? "进入 Antigravity 详情" : "View Antigravity Details";
    sessionHeadTitle = isZh ? "近期推理流水记录" : "Recent Inference Stream";

    const cacheHitRate = ((usage.cached_tokens / Math.max(1, usage.input_tokens + usage.cached_tokens)) * 100).toFixed(1);
    stats = [
      {
        label: isZh ? `${range} 全量模型吞吐` : `${range} Total Throughput`,
        value: formatCompact(total),
        sub: isZh ? "含上下文缓存吞吐" : "Full context throughput",
      },
      {
        label: isZh ? "新输入 Token" : "New Input Tokens",
        value: formatCompact(usage.input_tokens),
        sub: isZh ? "未缓存新增 Prompt" : "Uncached prompt delta",
      },
      {
        label: isZh ? "生成输出 Token" : "Generated Output",
        value: formatCompact(usage.output_tokens),
        sub: isZh ? "代码与思考推理" : "Generated code & text",
      },
      {
        label: isZh ? "上下文缓存命中" : "Cached Context",
        value: formatCompact(usage.cached_tokens),
        sub: isZh ? `缓存命中率 ${cacheHitRate}%` : `${cacheHitRate}% cache hit rate`,
      },
    ];

    const inputTotal = usage.input_tokens + usage.output_tokens + usage.cached_tokens || 1;
    breakdownTotalStr = `${formatCompact(total)} Tokens`;
    slices = [
      {
        label: isZh ? "新输入 Token" : "New Input Tokens",
        amount: usage.input_tokens,
        formattedAmount: usage.input_tokens.toLocaleString(),
        percent: Math.round((usage.input_tokens / inputTotal) * 100),
        color: "#3b82f6",
      },
      {
        label: isZh ? "生成输出 Token" : "Generated Output",
        amount: usage.output_tokens,
        formattedAmount: usage.output_tokens.toLocaleString(),
        percent: Math.round((usage.output_tokens / inputTotal) * 100),
        color: "#22c55e",
      },
      {
        label: isZh ? "缓存读取 Token" : "Cached Tokens",
        amount: usage.cached_tokens,
        formattedAmount: usage.cached_tokens.toLocaleString(),
        percent: Math.round((usage.cached_tokens / inputTotal) * 100),
        color: "#a855f7",
      },
    ];

    waveformValues = history.map((p) => p.antigravity_tokens ?? 0);
  } else if (selectedKey === "codex") {
    tintColor = "var(--v-purple)";
    targetView = "codex";
    const codex = snapshot.codex;
    const total = getRangeTokenTotal(codex, range);
    const usage = getRangeUsage(codex, range);

    title = isZh ? "OpenAI Codex CLI" : "OpenAI Codex CLI";
    subtitle = `${codex.model || "gpt-4o"} · ${codex.online ? (isZh ? "活跃" : "Active") : (isZh ? "待命" : "Idle")}`;
    icon = <CodeIcon style={{ color: "#a855f7" }} />;
    targetAction = isZh ? "进入 Codex 详情" : "View Codex Details";
    sessionHeadTitle = isZh ? "活跃会话贡献排行" : "Top Active Sessions";
    sessionCountStr = codexData?.sessions ? `${codexData.sessions.length} sessions` : "";

    stats = [
      {
        label: isZh ? `${range} 累计 Token` : `${range} Total Tokens`,
        value: formatCompact(total),
        sub: isZh ? "自然日去重账本" : "Deduplicated ledger",
      },
      {
        label: isZh ? "输入 Token" : "Input Tokens",
        value: formatCompact(usage.input_tokens),
        sub: isZh ? "Prompt 提示词" : "Prompt tokens",
      },
      {
        label: isZh ? "输出 Token" : "Output Tokens",
        value: formatCompact(usage.output_tokens),
        sub: isZh ? "补全与回答" : "Completions",
      },
      {
        label: isZh ? "缓存命中 Token" : "Cached Tokens",
        value: formatCompact(usage.cached_tokens),
        sub: isZh ? `会话次数: ${usage.interactions}` : `${usage.interactions} sessions`,
      },
    ];

    const inputTotal = usage.input_tokens + usage.output_tokens + usage.cached_tokens || 1;
    breakdownTotalStr = `${formatCompact(total)} Tokens`;
    slices = [
      {
        label: isZh ? "输入 Token" : "Input Tokens",
        amount: usage.input_tokens,
        formattedAmount: usage.input_tokens.toLocaleString(),
        percent: Math.round((usage.input_tokens / inputTotal) * 100),
        color: "#3b82f6",
      },
      {
        label: isZh ? "输出 Token" : "Output Tokens",
        amount: usage.output_tokens,
        formattedAmount: usage.output_tokens.toLocaleString(),
        percent: Math.round((usage.output_tokens / inputTotal) * 100),
        color: "#22c55e",
      },
      {
        label: isZh ? "缓存命中 Token" : "Cached Tokens",
        amount: usage.cached_tokens,
        formattedAmount: usage.cached_tokens.toLocaleString(),
        percent: Math.round((usage.cached_tokens / inputTotal) * 100),
        color: "#a855f7",
      },
    ];

    waveformValues = history.map((p) => p.codex_tokens ?? 0);
  } else if (selectedKey === "ollama") {
    tintColor = "var(--v-cyan)";
    targetView = "ollama";
    const ol = snapshot.ollama;
    const total = getRangeTokenTotal(ol, range);

    title = isZh ? "Ollama 本地推理引擎" : "Ollama Local Engine";
    subtitle = `${ol.model || "本地模型"} · ${ol.online ? (isZh ? "在线" : "Online") : (isZh ? "未启动" : "Offline")}`;
    icon = <ModelIcon style={{ color: "#06b6d4" }} />;
    targetAction = isZh ? "进入 Ollama 详情" : "View Ollama Details";
    sessionHeadTitle = isZh ? "推理服务活动" : "Inference Activity";

    stats = [
      {
        label: isZh ? "实时吞吐速率" : "Live Throughput",
        value: `${ol.tokens_per_second.toFixed(1)} T/s`,
        sub: isZh ? `峰值 ${ol.last_tokens_per_second.toFixed(1)} T/s` : `Peak ${ol.last_tokens_per_second.toFixed(1)} T/s`,
      },
      {
        label: isZh ? `${range} 产出 Token` : `${range} Tokens`,
        value: formatCompact(total),
        sub: isZh ? "今日推理累计" : "Cumulative output",
      },
      {
        label: isZh ? "上下文窗口占用" : "Context Usage",
        value: `${formatPercent(ol.context_used, ol.context_size).toFixed(0)}%`,
        sub: `${ol.context_used.toLocaleString()} / ${ol.context_size.toLocaleString()}`,
      },
      {
        label: isZh ? "活动状态" : "Run Status",
        value: ol.status.toUpperCase(),
        sub: isZh ? `并发请求: ${ol.inflight_requests}` : `${ol.inflight_requests} in-flight`,
      },
    ];

    const ctxUsed = ol.context_used;
    const ctxRemaining = Math.max(0, ol.context_size - ol.context_used);
    const ctxTotal = ol.context_size || 1;
    breakdownTitle = isZh ? "上下文窗口分布" : "Context Window Breakdown";
    breakdownTotalStr = `${ol.context_size.toLocaleString()} Tokens`;
    slices = [
      {
        label: isZh ? "已占用上下文" : "Used Context",
        amount: ctxUsed,
        formattedAmount: ctxUsed.toLocaleString(),
        percent: Math.round((ctxUsed / ctxTotal) * 100),
        color: "#06b6d4",
      },
      {
        label: isZh ? "可用上下文余量" : "Available Space",
        amount: ctxRemaining,
        formattedAmount: ctxRemaining.toLocaleString(),
        percent: Math.round((ctxRemaining / ctxTotal) * 100),
        color: "#2a2b34",
      },
    ];

    waveformValues = history.map((p) => (p.ollama_tokens_per_second > 0 ? p.ollama_tokens_per_second : p.ollama_tokens));
  } else if (selectedKey === "gpu") {
    tintColor = "var(--v-pink)";
    targetView = "hardware";
    const hw = snapshot.hardware;

    title = isZh ? "GPU 硬件加速单元" : "GPU Hardware Acceleration";
    subtitle = `${hw.gpu_name || "NVIDIA GPU"} · ${hw.gpu_available ? (isZh ? "已就绪" : "Ready") : (isZh ? "未检测到" : "Not Found")}`;
    icon = <HardwareIcon style={{ color: "#ec4899" }} />;
    targetAction = isZh ? "进入硬件遥测" : "Hardware Telemetry";
    sessionHeadTitle = isZh ? "加速架构与传感器" : "Architecture & Telemetry";

    stats = [
      {
        label: isZh ? "GPU 核心负载" : "GPU Core Load",
        value: `${hw.gpu_usage}%`,
        sub: isZh ? "实时算力占用" : "Compute load",
      },
      {
        label: isZh ? "显存使用率 (VRAM)" : "VRAM Allocation",
        value: `${hw.vram_used_gb.toFixed(1)} GB`,
        sub: `${isZh ? "总量" : "Total"}: ${hw.vram_total_gb.toFixed(1)} GB`,
      },
      {
        label: isZh ? "核心工作温度" : "GPU Temperature",
        value: hw.gpu_temperature_c !== null ? `${hw.gpu_temperature_c}°C` : "N/A",
        sub: isZh ? "散热风扇转速稳定" : "Thermals stable",
      },
      {
        label: isZh ? "实时运行功耗" : "Power Draw",
        value: hw.gpu_power_w !== null ? `${hw.gpu_power_w} W` : "N/A",
        sub: isZh ? "板载功耗传感器" : "Board power draw",
      },
    ];

    const vramUsed = hw.vram_used_gb;
    const vramFree = Math.max(0, hw.vram_total_gb - hw.vram_used_gb);
    const vramTotal = hw.vram_total_gb || 1;
    breakdownTitle = isZh ? "显存分配构成" : "VRAM Allocation Breakdown";
    breakdownTotalStr = `${hw.vram_total_gb.toFixed(1)} GB`;
    slices = [
      {
        label: isZh ? "模型推理占用" : "Model VRAM Used",
        amount: vramUsed,
        formattedAmount: `${vramUsed.toFixed(1)} GB`,
        percent: Math.round((vramUsed / vramTotal) * 100),
        color: "#ec4899",
      },
      {
        label: isZh ? "可用空闲显存" : "Free VRAM",
        amount: vramFree,
        formattedAmount: `${vramFree.toFixed(1)} GB`,
        percent: Math.round((vramFree / vramTotal) * 100),
        color: "#2a2b34",
      },
    ];

    waveformValues = history.map((p) => p.gpu_usage ?? 0);
  } else if (selectedKey === "host") {
    tintColor = "var(--v-green)";
    targetView = "hardware";
    const hw = snapshot.hardware;

    title = isZh ? "主机计算与物理内存" : "Host CPU & Physical Memory";
    subtitle = `${hw.cpu_frequency_mhz} MHz · ${formatDuration(hw.uptime_seconds, isZh ? "zh" : "en")}`;
    icon = <HardwareIcon style={{ color: "#22c55e" }} />;
    targetAction = isZh ? "进入硬件遥测" : "Hardware Telemetry";
    sessionHeadTitle = isZh ? "主机物理资源拓扑" : "Physical Resource Topology";

    stats = [
      {
        label: isZh ? "CPU 总体负载" : "CPU Utilization",
        value: `${hw.cpu_usage}%`,
        sub: isZh ? "全部物理核心平均" : "All physical cores",
      },
      {
        label: isZh ? "物理内存占用" : "RAM Usage",
        value: `${hw.ram_used_gb.toFixed(1)} GB`,
        sub: `${isZh ? "物理总内存" : "Total"}: ${hw.ram_total_gb.toFixed(1)} GB`,
      },
      {
        label: isZh ? "核心工作主频" : "Clock Frequency",
        value: `${hw.cpu_frequency_mhz} MHz`,
        sub: isZh ? "动态调度频段" : "Dynamic scaling",
      },
      {
        label: isZh ? "系统运行时长" : "System Uptime",
        value: formatDuration(hw.uptime_seconds, isZh ? "zh" : "en"),
        sub: isZh ? "主机正常运行" : "Continuous uptime",
      },
    ];

    const ramUsed = hw.ram_used_gb;
    const ramFree = Math.max(0, hw.ram_total_gb - hw.ram_used_gb);
    const ramTotal = hw.ram_total_gb || 1;
    breakdownTitle = isZh ? "主机内存分配构成" : "Host Memory Allocation";
    breakdownTotalStr = `${hw.ram_total_gb.toFixed(1)} GB`;
    slices = [
      {
        label: isZh ? "系统与应用已用" : "Used RAM",
        amount: ramUsed,
        formattedAmount: `${ramUsed.toFixed(1)} GB`,
        percent: Math.round((ramUsed / ramTotal) * 100),
        color: "#22c55e",
      },
      {
        label: isZh ? "空闲物理内存" : "Free RAM",
        amount: ramFree,
        formattedAmount: `${ramFree.toFixed(1)} GB`,
        percent: Math.round((ramFree / ramTotal) * 100),
        color: "#2a2b34",
      },
    ];

    waveformValues = history.map((p) => p.cpu_usage ?? 0);
  } else {
    // volume mode
    tintColor = "var(--v-blue)";
    targetView = "operations";
    const olTotal = getRangeTokenTotal(snapshot.ollama, range);
    const codexTotal = getRangeTokenTotal(snapshot.codex, range);
    const agTotal = getRangeTokenTotal(snapshot.antigravity, range);
    const combTotal = olTotal + codexTotal + agTotal;

    title = isZh ? "统一 Token 产出账本" : "Unified Token Output Ledger";
    subtitle = isZh ? "三端模型跨源聚合统计" : "Multi-provider telemetry aggregation";
    icon = (
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#3b82f6" strokeWidth="2">
        <path d="M18 20V10M12 20V4M6 20v-6" />
      </svg>
    );
    targetAction = isZh ? "查看全量请求" : "View Requests";
    sessionHeadTitle = isZh ? "三端贡献流水分布" : "Provider Contribution Stream";

    const olPct = combTotal > 0 ? Math.round((olTotal / combTotal) * 100) : 0;
    const codexPct = combTotal > 0 ? Math.round((codexTotal / combTotal) * 100) : 0;
    const agPct = combTotal > 0 ? Math.round((agTotal / combTotal) * 100) : 0;

    stats = [
      {
        label: isZh ? `${range} 三端产出总量` : `${range} Combined Tokens`,
        value: formatCompact(combTotal),
        sub: isZh ? "Ollama + Codex + Antigravity" : "All three engines",
      },
      {
        label: "Antigravity",
        value: formatCompact(agTotal),
        sub: `${agPct}% ${isZh ? "全局占比" : "share"}`,
      },
      {
        label: "Codex",
        value: formatCompact(codexTotal),
        sub: `${codexPct}% ${isZh ? "全局占比" : "share"}`,
      },
      {
        label: "Ollama",
        value: formatCompact(olTotal),
        sub: `${olPct}% ${isZh ? "全局占比" : "share"}`,
      },
    ];

    breakdownTitle = isZh ? "三端模型份额构成" : "Provider Token Share";
    breakdownTotalStr = `${formatCompact(combTotal)} Tokens`;
    slices = [
      {
        label: "Antigravity",
        amount: agTotal,
        formattedAmount: agTotal.toLocaleString(),
        percent: agPct,
        color: "#f59e0b",
      },
      {
        label: "Codex",
        amount: codexTotal,
        formattedAmount: codexTotal.toLocaleString(),
        percent: codexPct,
        color: "#a855f7",
      },
      {
        label: "Ollama",
        amount: olTotal,
        formattedAmount: olTotal.toLocaleString(),
        percent: olPct,
        color: "#06b6d4",
      },
    ];

    waveformValues = history.map(
      (p) => (p.ollama_tokens ?? 0) + (p.codex_tokens ?? 0) + (p.antigravity_tokens ?? 0)
    );
  }

  // 计算波形图 SVG 坐标
  const chartHeight = 110;
  const chartWidth = 100;
  const safeChartValues = waveformValues.length > 0 ? waveformValues : [0, 0];
  const chartMin = Math.min(...safeChartValues);
  const chartMax = Math.max(...safeChartValues);
  const chartSpan = chartMax - chartMin || (chartMax > 0 ? chartMax : 1);

  const chartPoints = safeChartValues.map((val, idx) => {
    const x = safeChartValues.length > 1 ? (idx / (safeChartValues.length - 1)) * chartWidth : 50;
    const norm = (val - chartMin) / chartSpan;
    const y = 8 + (1 - norm) * (chartHeight - 20);
    return { x, y };
  });

  const chartLineD = chartPoints.length > 0
    ? `M ${chartPoints.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L ")}`
    : "";

  const chartAreaD = chartPoints.length > 0
    ? `${chartLineD} L ${chartWidth},${chartHeight} L 0,${chartHeight} Z`
    : "";

  // 鼠标交互游标事件
  const handleChartMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!chartSvgRef.current || safeChartValues.length <= 1) return;
    const rect = chartSvgRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const relX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const idx = Math.round(relX * (safeChartValues.length - 1));
    setHoverChartIndex(idx);
  };

  const handleChartMouseLeave = () => {
    setHoverChartIndex(null);
  };

  const activeWavePt = hoverChartIndex !== null && chartPoints[hoverChartIndex] ? chartPoints[hoverChartIndex] : null;
  const activeWaveVal = hoverChartIndex !== null && safeChartValues[hoverChartIndex] !== undefined ? safeChartValues[hoverChartIndex] : null;

  const getWaveTimeLabel = (idx: number) => {
    if (history[idx]?.timestamp) {
      try {
        const d = new Date(history[idx].timestamp);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
      } catch {
        // fallback
      }
    }
    const totalPts = safeChartValues.length - 1 || 1;
    const hrs = Math.round(24 * (1 - idx / totalPts));
    return hrs === 0 ? (isZh ? "当前" : "Now") : `-${hrs}h`;
  };

  // 提取会话与流水流列表
  const agSignals = snapshot.recent_signals.filter((s) => s.source.toLowerCase().includes("antigravity")).slice(0, 3);
  const olSignals = snapshot.recent_signals.filter((s) => s.source.toLowerCase().includes("ollama")).slice(0, 3);

  return (
    <aside className="vitals-right-col" aria-label="Details Inspector">
      <div className="inspector-panel" key={selectedKey}>
        {/* 顶部身份铭牌 */}
        <div className="inspector-head">
          <div className="inspector-identity">
            <div className="inspector-icon">{icon}</div>
            <div className="inspector-titles">
              <span className="inspector-title">{title}</span>
              <span className="inspector-subtitle">{subtitle}</span>
            </div>
          </div>
        </div>

        {/* 4 宫格快捷指标卡 */}
        <div className="inspector-stats-grid">
          {stats.map((s, idx) => (
            <div className="inspector-stat-tile" key={idx}>
              <span>{s.label}</span>
              <strong>{s.value}</strong>
              <small>{s.sub}</small>
            </div>
          ))}
        </div>

        {/* 多色分段比例条与清单 */}
        <div className="breakdown-box">
          <div className="breakdown-head">
            <span>{breakdownTitle}</span>
            <span style={{ fontFamily: "var(--v-font-mono)", fontSize: "11px", color: "var(--v-ink-2)" }}>
              {breakdownTotalStr}
            </span>
          </div>

          {/* 分段长条 */}
          <div className="segmented-track">
            {slices.map((slice, idx) => (
              <div
                key={idx}
                className="segment-slice"
                style={{
                  width: `${slice.percent}%`,
                  backgroundColor: slice.color,
                }}
                title={`${slice.label}: ${slice.percent}%`}
              />
            ))}
          </div>

          {/* 分级列表项 */}
          <div className="breakdown-list">
            {slices.map((slice, idx) => (
              <div className="breakdown-row" key={idx}>
                <div className="breakdown-row-left">
                  <span className="breakdown-dot" style={{ backgroundColor: slice.color }} />
                  <span>{slice.label}</span>
                </div>
                <div className="breakdown-row-right">
                  <span className="breakdown-percent">{slice.percent}%</span>
                  <span className="breakdown-amount">{slice.formattedAmount}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 阶段 3：活跃会话与流速明细 */}
        <div className="inspector-session-box">
          <div className="inspector-session-head">
            <span>{sessionHeadTitle}</span>
            <span style={{ fontSize: "10.5px", color: "var(--v-ink-3)" }}>{sessionCountStr}</span>
          </div>

          <div className="inspector-session-list">
            {selectedKey === "codex" && codexData?.sessions && codexData.sessions.length > 0 ? (
              codexData.sessions.slice(0, 3).map((sess, idx) => (
                <div className="inspector-session-item" key={idx}>
                  <div className="session-left">
                    <span className="session-badge">{sess.session || `S-${sess.session_id.slice(0, 6)}`}</span>
                    <span className="session-meta" title={`${sess.workspace} · ${sess.model}`}>
                      {sess.workspace} · {sess.model}
                    </span>
                  </div>
                  <div className="session-right">
                    <span className="session-tokens">{formatCompact(sess.total_tokens)}</span>
                    <span className="session-share">{sess.share_percent.toFixed(1)}%</span>
                  </div>
                </div>
              ))
            ) : selectedKey === "antigravity" && agSignals.length > 0 ? (
              agSignals.map((sig, idx) => (
                <div className="inspector-session-item" key={idx}>
                  <div className="session-left">
                    <span className="session-badge" style={{ color: "#f59e0b" }}>AG</span>
                    <span className="session-meta" title={sig.detail}>
                      {sig.detail}
                    </span>
                  </div>
                  <div className="session-right">
                    <span className="session-share">{formatRelativeTime(sig.timestamp, isZh)}</span>
                  </div>
                </div>
              ))
            ) : selectedKey === "ollama" && olSignals.length > 0 ? (
              olSignals.map((sig, idx) => (
                <div className="inspector-session-item" key={idx}>
                  <div className="session-left">
                    <span className="session-badge" style={{ color: "#06b6d4" }}>OLLAMA</span>
                    <span className="session-meta" title={sig.detail}>
                      {sig.detail}
                    </span>
                  </div>
                  <div className="session-right">
                    <span className="session-share">{formatRelativeTime(sig.timestamp, isZh)}</span>
                  </div>
                </div>
              ))
            ) : selectedKey === "gpu" ? (
              <div className="inspector-session-item">
                <div className="session-left">
                  <span className="session-badge" style={{ color: "#ec4899" }}>GPU</span>
                  <span className="session-meta">
                    {snapshot.hardware.gpu_name || "DirectX/Vulkan Hardware Device"}
                  </span>
                </div>
                <div className="session-right">
                  <span className="session-tokens">{snapshot.hardware.vram_used_gb.toFixed(1)}G</span>
                </div>
              </div>
            ) : selectedKey === "host" ? (
              <div className="inspector-session-item">
                <div className="session-left">
                  <span className="session-badge" style={{ color: "#22c55e" }}>HOST</span>
                  <span className="session-meta">
                    {snapshot.hardware.cpu_frequency_mhz} MHz · {snapshot.hardware.ram_used_gb.toFixed(1)}G RAM
                  </span>
                </div>
                <div className="session-right">
                  <span className="session-tokens">{snapshot.hardware.cpu_usage}%</span>
                </div>
              </div>
            ) : (
              <div className="inspector-session-item">
                <div className="session-left">
                  <span className="session-badge" style={{ color: "#3b82f6" }}>CROSS-ORIGIN</span>
                  <span className="session-meta">{isZh ? "三源协同捕获" : "Tri-engine unified capture"}</span>
                </div>
                <div className="session-right">
                  <span className="session-tokens">{isZh ? "正常" : "Nominal"}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 24H 交互式波动波形图 */}
        <div className="inspector-chart-box">
          <div className="inspector-chart-head">
            <span className="inspector-chart-title">
              {isZh ? "24小时波动趋势" : "24h Activity Waveform"}
            </span>
            <span className="inspector-chart-scale">
              {chartMax > 0 ? `Max: ${formatCompact(chartMax)}` : "Baseline"}
            </span>
          </div>

          <div className="inspector-chart-container" onMouseLeave={handleChartMouseLeave}>
            {activeWavePt && activeWaveVal !== null && hoverChartIndex !== null && (
              <div
                className="inspector-chart-tooltip"
                style={{ left: `${activeWavePt.x}%` }}
              >
                {formatCompact(activeWaveVal)} · {getWaveTimeLabel(hoverChartIndex)}
              </div>
            )}

            <svg
              ref={chartSvgRef}
              viewBox={`0 0 ${chartWidth} ${chartHeight}`}
              preserveAspectRatio="none"
              className="inspector-chart-svg"
              style={{ cursor: "crosshair" }}
              onMouseMove={handleChartMouseMove}
              aria-hidden="true"
            >
              <defs>
                <linearGradient id={`inspector-wave-grad-${chartGradId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={tintColor} stopOpacity="0.32" />
                  <stop offset="85%" stopColor={tintColor} stopOpacity="0.04" />
                  <stop offset="100%" stopColor={tintColor} stopOpacity="0" />
                </linearGradient>
              </defs>

              {/* 3 条背景横线 */}
              <line x1="0" y1="25" x2="100" y2="25" stroke="rgba(255,255,255,0.06)" strokeDasharray="2,2" strokeWidth="0.5" />
              <line x1="0" y1="58" x2="100" y2="58" stroke="rgba(255,255,255,0.06)" strokeDasharray="2,2" strokeWidth="0.5" />
              <line x1="0" y1="92" x2="100" y2="92" stroke="rgba(255,255,255,0.06)" strokeDasharray="2,2" strokeWidth="0.5" />

              {chartAreaD && (
                <path d={chartAreaD} fill={`url(#inspector-wave-grad-${chartGradId})`} />
              )}

              {chartLineD && (
                <path
                  d={chartLineD}
                  fill="none"
                  stroke={tintColor}
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
              )}

              {/* 鼠标悬停标尺虚线 */}
              {activeWavePt && (
                <line
                  x1={activeWavePt.x}
                  y1={0}
                  x2={activeWavePt.x}
                  y2={chartHeight}
                  className="sparkline-scrubber-line"
                />
              )}

              {/* 鼠标悬停指示高亮点 */}
              {activeWavePt && (
                <circle
                  cx={activeWavePt.x}
                  cy={activeWavePt.y}
                  r="3.8"
                  fill={tintColor}
                  stroke="#ffffff"
                  strokeWidth="1.8"
                />
              )}
            </svg>
          </div>

          <div className="inspector-chart-footer">
            <span>-24h</span>
            <span>{isZh ? "当前时刻" : "Now"}</span>
          </div>
        </div>

        {/* 底部操作项 */}
        <div className="inspector-actions">
          <button
            type="button"
            className="btn-vitals-primary"
            onClick={() => onNavigate(targetView)}
          >
            {targetAction} →
          </button>
          <button
            type="button"
            className="btn-vitals-quiet"
            onClick={() => onNavigate("operations")}
          >
            {isZh ? "日对账核验" : "Reconciliation"}
          </button>
        </div>
      </div>
    </aside>
  );
}
