interface SparklineProps {
  values: number[];
  warning?: boolean;
}

export function Sparkline({ values, warning = false }: SparklineProps) {
  // 边界：没有真实采样时显示缺失态，不能用 [0, 0] 伪造一条零值趋势。
  if (values.length === 0) {
    return <span className="sparkline sparkline-empty" aria-hidden="true">—</span>;
  }
  const safeValues = values.length > 1 ? values : [values[0], values[0]];
  const min = Math.min(...safeValues);
  const max = Math.max(...safeValues);
  const span = max - min || 1;
  const points = safeValues
    .map((value, index) => {
      const x = (index / (safeValues.length - 1)) * 100;
      const y = 28 - ((value - min) / span) * 24;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg className={`sparkline${warning ? " is-warning" : ""}`} viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} />
    </svg>
  );
}
