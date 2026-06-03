import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { Activity, Bot, Database, Play, RefreshCw, Shield, Terminal, UploadCloud } from "lucide-react";
import "./styles.css";

const queryClient = new QueryClient();
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001";
type ActiveView = "dashboard" | "data" | "agent" | "routes";

const cycles = [
  {
    id: "2026-06-btc-vegas",
    pair: "BTC / Vegas EMA",
    stage: "Stage 1A",
    train: "Feb 17 - May 17",
    validation: "May 18 - May 31",
    oos: "Jun 01 - Jun 14",
    status: "Agent audit ready"
  },
  {
    id: "2026-06-eth-bollinger",
    pair: "ETH / Bollinger",
    stage: "Stage 0",
    train: "Feb 17 - May 17",
    validation: "May 18 - May 31",
    oos: "Jun 01 - Jun 14",
    status: "Travel scoring"
  }
];

const routes = [
  {
    id: "btc-vegas-live",
    asset: "BTC-USDT-SWAP",
    strategy: "vegas_reclaim@0.1.0",
    adapter: "OKX",
    blockers: ["promotion", "warmup", "manual arm"],
    enabled: false
  },
  {
    id: "eth-bollinger-paper",
    asset: "ETH-USDT-SWAP",
    strategy: "bb_mean_revert@0.1.0",
    adapter: "OKX",
    blockers: ["stage 4"],
    enabled: false
  }
];

const metrics = [
  { label: "Engines", value: "2", detail: "registered" },
  { label: "Strategies", value: "2", detail: "versioned" },
  { label: "WF Runs", value: "2", detail: "active" },
  { label: "Live Routes", value: "0", detail: "armed" }
];

type Dataset = {
  dataset_id: string;
  asset: string;
  instrument: string;
  data_type: string;
  timeframe: string | null;
  data_origin: string;
  start_ts: string | null;
  end_ts: string | null;
  row_count: number | null;
  storage_backend: string;
  storage_uri: string;
  quality_status: string;
  ingestion_version: string;
};

type CatalogAsset = {
  asset: string;
  datasets: Dataset[];
};

type CatalogResponse = {
  summary: {
    assets: number;
    datasets: number;
    data_types: string[];
  };
  assets: CatalogAsset[];
};

type RefreshPlan = {
  dataset_id: string;
  status: string;
  from_ts?: string;
  to_ts?: string;
  reason?: string;
};

async function fetchCatalog(): Promise<CatalogResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/market-data/catalog`);
  if (!response.ok) {
    throw new Error("Failed to load market data catalog");
  }
  return response.json();
}

async function refreshDataset(datasetId: string): Promise<RefreshPlan> {
  const response = await fetch(`${API_BASE_URL}/api/v1/market-data/${datasetId}/refresh`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error("Failed to build refresh plan");
  }
  return response.json();
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TerminalApp />
    </QueryClientProvider>
  );
}

function TerminalApp() {
  const [activeView, setActiveView] = React.useState<ActiveView>("dashboard");
  const catalogQuery = useQuery({ queryKey: ["market-data-catalog"], queryFn: fetchCatalog });
  const refreshMutation = useMutation({ mutationFn: refreshDataset });
  const catalog = catalogQuery.data;
  const dynamicMetrics = catalog
    ? [
        { label: "Assets", value: String(catalog.summary.assets), detail: "cataloged" },
        { label: "Datasets", value: String(catalog.summary.datasets), detail: "registered" },
        { label: "Types", value: String(catalog.summary.data_types.length), detail: catalog.summary.data_types.join(", ") || "none" },
        { label: "Live Routes", value: "0", detail: "armed" }
      ]
    : metrics;

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <Terminal size={22} />
          <span>Motis</span>
        </div>
        <nav>
          <button className={activeView === "dashboard" ? "active" : ""} type="button" onClick={() => setActiveView("dashboard")}><Activity size={18} />Dashboard</button>
          <button className={activeView === "data" ? "active" : ""} type="button" onClick={() => setActiveView("data")}><Database size={18} />Data</button>
          <button className={activeView === "agent" ? "active" : ""} type="button" onClick={() => setActiveView("agent")}><Bot size={18} />Agent Lab</button>
          <button className={activeView === "routes" ? "active" : ""} type="button" onClick={() => setActiveView("routes")}><Shield size={18} />Routes</button>
        </nav>
      </aside>

      <main className="workspace">
        <section className="topbar" id="dashboard">
          <div>
            <h1>Deterministic Quant Terminal</h1>
            <p>Local research, walk-forward scoring, agent iteration, and gated execution.</p>
          </div>
          <div className="topbar-actions">
            <button type="button" onClick={() => catalogQuery.refetch()}><RefreshCw size={16} />Sync Data</button>
            <button type="button" className="primary"><Play size={16} />Run Cycle</button>
          </div>
        </section>

        <section className="metric-grid" aria-label="System metrics">
          {dynamicMetrics.map((metric) => (
            <article className="metric" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.detail}</small>
            </article>
          ))}
        </section>

        {activeView === "data" && (
          <section className="content-grid">
            <DataCatalog
              catalog={catalog}
              loading={catalogQuery.isLoading}
              error={catalogQuery.error}
              refreshMutation={refreshMutation}
            />
          </section>
        )}

        {activeView === "dashboard" && (
          <section className="content-grid">
            <article className="panel large">
              <div className="panel-header">
                <h2>Walk-Forward Cycles</h2>
                <span className="pill">rolling_90d_14d_14d_weekly</span>
              </div>
              <div className="table">
                <div className="row header">
                  <span>Candidate</span>
                  <span>Stage</span>
                  <span>Train</span>
                  <span>Validation</span>
                  <span>Locked OOS</span>
                  <span>Status</span>
                </div>
                {cycles.map((cycle) => (
                  <div className="row" key={cycle.id}>
                    <span>{cycle.pair}</span>
                    <span>{cycle.stage}</span>
                    <span>{cycle.train}</span>
                    <span>{cycle.validation}</span>
                    <span>{cycle.oos}</span>
                    <span className="status">{cycle.status}</span>
                  </div>
                ))}
              </div>
            </article>
          </section>
        )}

        {activeView === "agent" && (
          <section className="content-grid">
          <article className="panel">
            <div className="panel-header">
              <h2>Agent Task</h2>
              <span className="pill amber">manual</span>
            </div>
            <p className="panel-copy">Stage 1A failure clusters are ready for a scoped task bundle.</p>
            <button type="button"><Bot size={16} />Generate Task</button>
          </article>
          </section>
        )}

        {activeView === "routes" && (
          <section className="content-grid">
          <article className="panel" id="routes">
            <div className="panel-header">
              <h2>Deployment Routes</h2>
              <span className="pill red">blocked</span>
            </div>
            <div className="route-list">
              {routes.map((route) => (
                <div className="route" key={route.id}>
                  <strong>{route.asset}</strong>
                  <span>{route.strategy}</span>
                  <small>{route.adapter} blockers: {route.blockers.join(", ")}</small>
                </div>
              ))}
            </div>
          </article>
          </section>
        )}
      </main>
    </div>
  );
}

function DataCatalog({
  catalog,
  loading,
  error,
  refreshMutation
}: {
  catalog?: CatalogResponse;
  loading: boolean;
  error: Error | null;
  refreshMutation: ReturnType<typeof useMutation<RefreshPlan, Error, string>>;
}) {
  return (
    <article className="panel large" id="data">
      <div className="panel-header">
        <h2>Data Catalog</h2>
        <span className="pill">multi-type</span>
      </div>
      {loading && <p className="panel-copy">Loading local market data coverage...</p>}
      {error && <p className="panel-copy error-text">{error.message}</p>}
      {catalog && (
        <div className="asset-list">
          {catalog.assets.map((asset) => (
            <section className="asset-section" key={asset.asset}>
              <div className="asset-title">
                <strong>{asset.asset}</strong>
                <span>{asset.datasets.length} datasets</span>
              </div>
              <div className="dataset-grid">
                {asset.datasets.map((dataset) => (
                  <DatasetRow
                    dataset={dataset}
                    key={dataset.dataset_id}
                    refreshMutation={refreshMutation}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </article>
  );
}

function DatasetRow({
  dataset,
  refreshMutation
}: {
  dataset: Dataset;
  refreshMutation: ReturnType<typeof useMutation<RefreshPlan, Error, string>>;
}) {
  const canRefresh = dataset.data_type === "candles" && dataset.data_origin === "raw";
  const lastPlan = refreshMutation.data?.dataset_id === dataset.dataset_id ? refreshMutation.data : undefined;

  return (
    <div className="dataset-row">
      <div>
        <strong>{dataset.data_type}</strong>
        <span>{dataset.timeframe ?? "event"} · {dataset.data_origin}</span>
      </div>
      <span>{formatDate(dataset.start_ts)} - {formatDate(dataset.end_ts)}</span>
      <span>{formatNumber(dataset.row_count)} rows</span>
      <span className="status">{dataset.quality_status}</span>
      <button
        type="button"
        disabled={!canRefresh || refreshMutation.isPending}
        onClick={() => refreshMutation.mutate(dataset.dataset_id)}
        title={canRefresh ? "Plan candle fill to current time" : "Refresh is currently supported for raw candle datasets"}
      >
        <UploadCloud size={16} />Fill
      </button>
      {lastPlan && (
        <small className={lastPlan.status === "planned" ? "refresh-note" : "refresh-note blocked"}>
          {lastPlan.status === "planned"
            ? `${formatDate(lastPlan.from_ts ?? null)} -> ${formatDate(lastPlan.to_ts ?? null)}`
            : lastPlan.reason}
        </small>
      )}
    </div>
  );
}

function formatDate(value: string | null): string {
  if (!value) {
    return "n/a";
  }
  return value.slice(0, 10);
}

function formatNumber(value: number | null): string {
  return value === null ? "n/a" : value.toLocaleString();
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
