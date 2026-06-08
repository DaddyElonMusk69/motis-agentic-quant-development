import { Activity, CheckCircle2, Clock, Database, RadioTower } from "lucide-react";
import { API_BASE_URL, getStaticHealthSnapshot } from "../app/api";
import { DataTable } from "../components/DataTable";
import { FieldRow } from "../components/FieldRow";
import { StatusBadge } from "../components/StatusBadge";
import { TerminalPanel } from "../components/TerminalPanel";

const activityRows = [
  { time: "15:10:00 UTC", domain: "Trading", event: "AAVE route wake completed", result: "OK" },
  { time: "15:05:00 UTC", domain: "Execution", event: "Protection check held", result: "OK" },
  { time: "14:55:00 UTC", domain: "R&D", event: "Stage 4 promotion available", result: "Review" },
  { time: "14:40:00 UTC", domain: "Data", event: "Raw candle catalog unchanged", result: "Idle" }
];

export function DashboardPage() {
  const health = getStaticHealthSnapshot();

  return (
    <div className="page page--dashboard">
      <header className="dashboard-topbar">
        <div>
          <span className="eyebrow">Local operator console</span>
          <h1>Motis Quant Terminal</h1>
        </div>
        <div className="dashboard-topbar__status">
          <StatusBadge tone="info">API {health.api}</StatusBadge>
          <StatusBadge tone="idle">DB {health.database}</StatusBadge>
          <StatusBadge tone="idle">OKX CLI {health.okxCli}</StatusBadge>
          <span className="mono">{health.utc}</span>
        </div>
      </header>

      <section className="metric-strip" aria-label="Operational summary">
        <div className="metric-cell">
          <Activity aria-hidden="true" />
          <span>Active Routes</span>
          <strong>1</strong>
        </div>
        <div className="metric-cell">
          <Database aria-hidden="true" />
          <span>Canonical Data</span>
          <strong>Parquet</strong>
        </div>
        <div className="metric-cell">
          <RadioTower aria-hidden="true" />
          <span>Signal Engine</span>
          <strong>vegas_ema</strong>
        </div>
        <div className="metric-cell">
          <Clock aria-hidden="true" />
          <span>Next Wake</span>
          <strong>5m</strong>
        </div>
      </section>

      <div className="dashboard-grid">
        <TerminalPanel eyebrow={API_BASE_URL} title="System Readiness">
          <div className="field-stack">
            <FieldRow label="API surface" tone="warn" value="Static placeholder" />
            <FieldRow label="Backend contract" value="Unchanged" />
            <FieldRow label="Current app" value="v1 remains on 5173" />
            <FieldRow label="New app" value="v2 targets 5174" />
          </div>
        </TerminalPanel>

        <TerminalPanel title="Work Queue">
          <div className="attention-list">
            <div>
              <CheckCircle2 aria-hidden="true" />
              <span>Port API client after shell approval</span>
            </div>
            <div>
              <CheckCircle2 aria-hidden="true" />
              <span>Move Data page first for canonical coverage</span>
            </div>
            <div>
              <CheckCircle2 aria-hidden="true" />
              <span>Keep live controls route-scoped</span>
            </div>
          </div>
        </TerminalPanel>
      </div>

      <TerminalPanel title="Recent Activity">
        <DataTable
          columns={[
            { key: "time", header: "Time", render: (row) => <span className="mono">{row.time}</span> },
            { key: "domain", header: "Domain", render: (row) => row.domain },
            { key: "event", header: "Event", render: (row) => row.event },
            { key: "result", header: "Result", align: "right", render: (row) => <StatusBadge tone={row.result === "OK" ? "pass" : "idle"}>{row.result}</StatusBadge> }
          ]}
          getRowKey={(row) => `${row.time}-${row.event}`}
          rows={activityRows}
        />
      </TerminalPanel>
    </div>
  );
}
