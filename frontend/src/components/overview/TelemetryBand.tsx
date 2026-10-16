import type { CSSProperties } from "react";

import type { HardwareSnapshot, TrendPoint } from "../../types/dashboard";
import { formatPercent } from "../../utils/format";
import { useTranslation } from "react-i18next";
import { Sparkline } from "../common/Sparkline";

interface GaugeProps {
  label: string;
  value: string;
  percent: number;
  values: number[];
  warning?: boolean;
}

function Gauge({ label, value, percent, values, warning = false }: GaugeProps) {
  const safePercent = Math.min(100, Math.max(0, percent));
  // 处理：百分比同时供新横向进度条和旧版圆形仪表样式使用，便于渐进式升级。
  const style = {
    "--gauge-value": `${safePercent * 3.6}deg`,
    "--gauge-percent": `${safePercent}%`,
  } as CSSProperties;
  return (
    <div className={`gauge-cell${warning ? " is-warning" : ""}`}>
      <span className="gauge-label">{label}</span>
      <strong>{value}</strong>
      <div className="gauge" style={style}><span>{safePercent.toFixed(0)}%</span></div>
      <Sparkline values={values} warning={warning} />
    </div>
  );
}

interface TelemetryBandProps {
  hardware: HardwareSnapshot;
  history: TrendPoint[];
}

export function TelemetryBand({ hardware, history }: TelemetryBandProps) {
  const { t } = useTranslation();
  const tail = history.slice(-24);
  const ramPercent = formatPercent(hardware.ram_used_gb, hardware.ram_total_gb);
  const vramPercent = formatPercent(hardware.vram_used_gb, hardware.vram_total_gb);
  const temperaturePercent = Math.min(100, hardware.gpu_temperature_c ?? 0);
  const temperatureHistory = tail.flatMap((point) => (
    typeof point.gpu_temperature_c === "number" ? [point.gpu_temperature_c] : []
  ));

  return (
    <section className="panel telemetry-panel">
      <div className="panel-heading compact-heading"><h2>{t("hardware.title")}</h2><span className="panel-context">{t("hardware.host")}</span></div>
      <div className="telemetry-grid">
        <Gauge label="GPU" value={hardware.gpu_available ? `${hardware.gpu_usage.toFixed(0)}%` : "—"} percent={hardware.gpu_usage} values={tail.map((point) => point.gpu_usage)} warning={hardware.gpu_usage >= 90} />
        <Gauge label="VRAM" value={hardware.gpu_available ? `${hardware.vram_used_gb} / ${hardware.vram_total_gb} GB` : "—"} percent={vramPercent} values={tail.map((point) => point.vram_usage)} warning={vramPercent >= 90} />
        <Gauge label={t("hardware.temp")} value={hardware.gpu_temperature_c == null ? "—" : `${hardware.gpu_temperature_c.toFixed(0)}°C`} percent={temperaturePercent} values={temperatureHistory} warning={temperaturePercent >= 80} />
        <Gauge label="CPU" value={`${hardware.cpu_usage.toFixed(0)}%`} percent={hardware.cpu_usage} values={tail.map((point) => point.cpu_usage)} />
        <Gauge label="RAM" value={`${hardware.ram_used_gb} / ${hardware.ram_total_gb} GB`} percent={ramPercent} values={tail.map((point) => point.ram_usage)} />
        <dl className="hardware-details">
          <div><dt>{t("hardware.gpuModel")}</dt><dd>{hardware.gpu_name}</dd></div>
          <div><dt>{t("hardware.gpuPower")}</dt><dd>{hardware.gpu_power_w == null ? "—" : `${hardware.gpu_power_w.toFixed(0)} W`}</dd></div>
          <div><dt>{t("hardware.fanSpeed")}</dt><dd>{hardware.gpu_fan_percent == null ? "—" : `${hardware.gpu_fan_percent.toFixed(0)}%`}</dd></div>
          <div><dt>{t("hardware.cpuClock")}</dt><dd>{hardware.cpu_frequency_mhz ? `${hardware.cpu_frequency_mhz.toFixed(0)} MHz` : "—"}</dd></div>
          <div><dt>{t("nav.collector")}</dt><dd>{t("hardware.collectorInterval")}</dd></div>
        </dl>
      </div>
    </section>
  );
}
