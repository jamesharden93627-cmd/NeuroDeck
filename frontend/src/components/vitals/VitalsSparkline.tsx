import { useId, useRef, useState } from "react";
import { formatCompact } from "../../utils/format";

interface VitalsSparklineProps {
  values: number[];
  tintColor: string;
  height?: number;
  showArea?: boolean;
  unit?: string;
  formatValue?: (val: number) => string;
}

export function VitalsSparkline({
  values,
  tintColor,
  height = 38,
  showArea = true,
  unit = "",
  formatValue,
}: VitalsSparklineProps) {
  const gradientId = useId().replace(/:/g, "_");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const hasData = values && values.length > 0;
  const safeValues = hasData ? values : [0, 0];
  const min = Math.min(...safeValues);
  const max = Math.max(...safeValues);
  const span = max - min || (max > 0 ? max : 1);

  const paddingTop = 4;
  const paddingBottom = 4;
  const drawHeight = Math.max(10, height - paddingTop - paddingBottom);

  const points = safeValues.map((val, idx) => {
    const x = safeValues.length > 1 ? (idx / (safeValues.length - 1)) * 100 : 50;
    const normalized = (val - min) / span;
    const y = paddingTop + (1 - normalized) * drawHeight;
    return { x, y };
  });

  const lineD = points.length > 0
    ? `M ${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L ")}`
    : "";

  const areaD = points.length > 0
    ? `${lineD} L 100,${height} L 0,${height} Z`
    : "";

  const lastPoint = points[points.length - 1];

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current || safeValues.length <= 1) return;
    const rect = svgRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const relativeX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const idx = Math.round(relativeX * (safeValues.length - 1));
    setHoverIndex(idx);
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
  };

  const activePoint = hoverIndex !== null && points[hoverIndex] ? points[hoverIndex] : null;
  const activeValue = hoverIndex !== null && safeValues[hoverIndex] !== undefined ? safeValues[hoverIndex] : null;

  const displayFormatter = (val: number) => {
    if (formatValue) return formatValue(val);
    return `${formatCompact(val)}${unit ? ` ${unit}` : ""}`;
  };

  return (
    <div
      style={{ position: "relative", width: "100%", height: `${height}px` }}
      onMouseLeave={handleMouseLeave}
    >
      {/* 悬停微提示 Tooltip */}
      {activePoint && activeValue !== null && (
        <div
          className="sparkline-tooltip"
          style={{
            left: `${activePoint.x}%`,
          }}
        >
          {displayFormatter(activeValue)}
        </div>
      )}

      <svg
        ref={svgRef}
        viewBox={`0 0 100 ${height}`}
        preserveAspectRatio="none"
        className="vitals-sparkline-svg"
        style={{ width: "100%", height: "100%", overflow: "visible", cursor: "crosshair" }}
        onMouseMove={handleMouseMove}
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={`spark-grad-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={tintColor} stopOpacity="0.32" />
            <stop offset="80%" stopColor={tintColor} stopOpacity="0.04" />
            <stop offset="100%" stopColor={tintColor} stopOpacity="0" />
          </linearGradient>
        </defs>

        {showArea && areaD && (
          <path d={areaD} fill={`url(#spark-grad-${gradientId})`} />
        )}

        {lineD && (
          <path
            d={lineD}
            fill="none"
            stroke={tintColor}
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        )}

        {/* 鼠标悬停标尺虚线 */}
        {activePoint && (
          <line
            x1={activePoint.x}
            y1={0}
            x2={activePoint.x}
            y2={height}
            className="sparkline-scrubber-line"
          />
        )}

        {/* 鼠标悬停高亮点 */}
        {activePoint ? (
          <circle
            cx={activePoint.x}
            cy={activePoint.y}
            r="3.5"
            fill={tintColor}
            stroke="#ffffff"
            strokeWidth="1.5"
          />
        ) : (
          lastPoint && hasData && max > 0 && (
            <circle
              cx={lastPoint.x}
              cy={lastPoint.y}
              r="2.5"
              fill={tintColor}
              stroke="#18191c"
              strokeWidth="1"
            />
          )
        )}
      </svg>
    </div>
  );
}
