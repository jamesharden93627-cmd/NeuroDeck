import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const common = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
  "aria-hidden": true,
};

export function OverviewIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M3.5 10.5 12 3l8.5 7.5" />
      <path d="M5.5 9v11h13V9M9.5 20v-6h5v6" />
    </svg>
  );
}

export function ModelIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M8 9h8M8 13h5M8 17h8M12 2v3" />
    </svg>
  );
}

export function CodeIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="m8 6-5 6 5 6M16 6l5 6-5 6M14 3l-4 18" />
    </svg>
  );
}

/** 功能：请求分析使用独立柱状图标，窄屏仅图标导航时仍可区分 Codex。 */
export function AnalyticsIcon(props: IconProps) {
  return <svg {...common} {...props}><path d="M4 3v17h17M8 16v-5M13 16V6M18 16V9" /></svg>;
}

export function HardwareIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" />
    </svg>
  );
}

export function ChevronIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="m8 10 4 4 4-4" />
    </svg>
  );
}

/** 功能：Antigravity 导航图标，用中心射线向上的菱形象征 AI 模型推理。 */
export function AntigravityIcon(props: IconProps) {
  return (
    <svg {...common} {...props}>
      <path d="M12 3 5 12l7 9 7-9z" />
      <path d="M12 3v18M5 12h14" />
    </svg>
  );
}
