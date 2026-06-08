import type { ReactNode } from "react";

type StatusTone = "pass" | "risk" | "warn" | "info" | "idle" | "live";

type StatusBadgeProps = {
  children: ReactNode;
  tone?: StatusTone;
};

export function StatusBadge({ children, tone = "idle" }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
}
