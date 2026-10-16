import { useTranslation } from "react-i18next";

interface StatusDotProps {
  online: boolean;
  label?: string;
  warning?: boolean;
}

export function StatusDot({ online, label, warning = false }: StatusDotProps) {
  const { t } = useTranslation();
  const tone = warning ? "warning" : online ? "online" : "offline";
  return (
    <span className={`inline-status tone-${tone}`}>
      <span className="status-dot" />
      {label ?? t(online ? "common.online" : "common.offline")}
    </span>
  );
}
