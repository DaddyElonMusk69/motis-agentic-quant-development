import type { ReactNode } from "react";

type SplitPaneProps = {
  left: ReactNode;
  right: ReactNode;
  className?: string;
  leftLabel?: string;
  workbenchClassName?: string;
};

export function SplitPane({ className, left, right, leftLabel, workbenchClassName }: SplitPaneProps) {
  return (
    <div className={className ? `split-pane ${className}` : "split-pane"} aria-label={leftLabel}>
      <aside className="split-pane__list">{left}</aside>
      <section className={workbenchClassName ? `split-pane__workbench ${workbenchClassName}` : "split-pane__workbench"}>{right}</section>
    </div>
  );
}
