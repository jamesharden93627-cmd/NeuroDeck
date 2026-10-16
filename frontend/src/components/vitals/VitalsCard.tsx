import type { ReactNode } from "react";
import { VitalsSparkline } from "./VitalsSparkline";

export interface VitalsCardStat {
  label: string;
  value: string | number;
}

export interface VitalsCardProps {
  cardKey: string;
  title: string;
  icon: ReactNode;
  subtitle: string;
  figureValue: string | number;
  figureUnit: string;
  stats: [VitalsCardStat, VitalsCardStat, VitalsCardStat];
  sparklineValues: number[];
  tintColor: string;
  statusState?: "active" | "idle" | "offline";
  delta?: { text: string; positive?: boolean };
  sparklineUnit?: string;
  formatSparkline?: (val: number) => string;
  isSelected?: boolean;
  onClick?: () => void;
}

export function VitalsCard({
  title,
  icon,
  subtitle,
  figureValue,
  figureUnit,
  stats,
  sparklineValues,
  tintColor,
  statusState,
  delta,
  sparklineUnit,
  formatSparkline,
  isSelected = false,
  onClick,
}: VitalsCardProps) {
  return (
    <div
      className={`vitals-card ${isSelected ? "is-selected" : ""}`}
      style={{ "--card-tint": tintColor } as React.CSSProperties}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.();
        }
      }}
      aria-pressed={isSelected}
    >
      <div className="vitals-card-top">
        <div className="vitals-card-badge" style={{ color: tintColor }}>
          {statusState && (
            <span
              className={`card-pulse-dot is-${statusState}`}
              title={`Status: ${statusState}`}
              aria-hidden="true"
            />
          )}
          {icon}
          <span>{title}</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {delta && (
            <span
              className={`card-delta-badge ${delta.positive ? "is-positive" : "is-neutral"}`}
            >
              {delta.text}
            </span>
          )}
          <svg
            className="vitals-card-chevron"
            viewBox="0 0 24 24"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </div>
      </div>

      <div className="vitals-card-sub" title={subtitle}>
        {subtitle}
      </div>

      <div className="vitals-card-figure">
        <span className="figure-number">{figureValue}</span>
        <span className="figure-unit">{figureUnit}</span>
      </div>

      <div className="vitals-card-stats">
        {stats.map((stat, idx) => (
          <div className="card-stat-item" key={idx}>
            <span className="card-stat-label">{stat.label}</span>
            <span className="card-stat-val" title={String(stat.value)}>
              {stat.value}
            </span>
          </div>
        ))}
      </div>

      <div className="vitals-card-sparkline">
        <VitalsSparkline
          values={sparklineValues}
          tintColor={tintColor}
          unit={sparklineUnit}
          formatValue={formatSparkline}
        />
      </div>
    </div>
  );
}
