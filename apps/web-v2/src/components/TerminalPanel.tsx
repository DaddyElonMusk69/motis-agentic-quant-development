import type { ReactNode } from "react";

type TerminalPanelProps = {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
};

export function TerminalPanel({ title, eyebrow, children, actions, className }: TerminalPanelProps) {
  return (
    <section className={className ? `terminal-panel ${className}` : "terminal-panel"}>
      <header className="terminal-panel__header">
        <div>
          {eyebrow ? <span>{eyebrow}</span> : null}
          <h2>{title}</h2>
        </div>
        {actions ? <div className="terminal-panel__actions">{actions}</div> : null}
      </header>
      <div className="terminal-panel__body">{children}</div>
    </section>
  );
}
