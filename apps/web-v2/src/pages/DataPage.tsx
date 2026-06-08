import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Database, RefreshCw, Search, UploadCloud } from "lucide-react";
import {
  fetchDatasetCandles,
  fetchMarketDataCatalog,
  refreshMarketDataDataset,
  type CatalogResponse,
  type Dataset,
  type RefreshPlan
} from "../app/api";
import { formatCompactValue, formatNumber, formatTimestamp } from "../app/format";
import { queryClient } from "../app/queryClient";
import { useAppRouter } from "../app/router";
import { DataTable } from "../components/DataTable";
import { FieldRow } from "../components/FieldRow";
import { SplitPane } from "../components/SplitPane";
import { StatusBadge } from "../components/StatusBadge";
import { TerminalPanel } from "../components/TerminalPanel";

type DatasetTypeOption = {
  dataType: string;
  label: string;
  count: number;
};

function getSelectedAsset(catalog: CatalogResponse | undefined, searchParams: URLSearchParams): string {
  const requested = searchParams.get("asset");
  if (requested && catalog?.assets.some((asset) => asset.asset === requested)) {
    return requested;
  }
  return catalog?.assets[0]?.asset ?? "";
}

function getSelectedDataset(catalog: CatalogResponse | undefined, selectedAsset: string, searchParams: URLSearchParams): Dataset | undefined {
  const requestedDataset = searchParams.get("dataset");
  const allDatasets = catalog?.assets.flatMap((asset) => asset.datasets) ?? [];
  const requested = allDatasets.find((dataset) => dataset.dataset_id === requestedDataset);
  if (requested) {
    return requested;
  }
  const assetDatasets = catalog?.assets.find((asset) => asset.asset === selectedAsset)?.datasets ?? [];
  return assetDatasets[0] ?? allDatasets[0];
}

function getDataTypeOptions(catalog: CatalogResponse | undefined, selectedAsset: string): DatasetTypeOption[] {
  const datasets = catalog?.assets.find((asset) => asset.asset === selectedAsset)?.datasets ?? [];
  const counts = new Map<string, number>();
  for (const dataset of datasets) {
    counts.set(dataset.data_type, (counts.get(dataset.data_type) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([dataType, count]) => ({
      dataType,
      label: dataType === "candles" ? "Candle data" : titleize(dataType),
      count
    }));
}

function getSelectedDataType(catalog: CatalogResponse | undefined, selectedAsset: string, searchParams: URLSearchParams): string {
  const requested = searchParams.get("data_type") ?? searchParams.get("filter");
  const options = getDataTypeOptions(catalog, selectedAsset);
  if (requested && options.some((option) => option.dataType === requested)) {
    return requested;
  }
  return options[0]?.dataType ?? "";
}

function updateDataUrl(next: { asset?: string; dataset?: string; dataType?: string }) {
  const params = new URLSearchParams(window.location.search);
  if (next.asset !== undefined) {
    params.set("asset", next.asset);
  }
  if (next.dataset !== undefined) {
    params.set("dataset", next.dataset);
  }
  if (next.dataType !== undefined) {
    params.set("data_type", next.dataType);
    params.delete("filter");
  }
  const query = params.toString();
  const nextUrl = `/data${query ? `?${query}` : ""}`;
  if (`${window.location.pathname}${window.location.search}` === nextUrl) {
    return;
  }
  window.history.pushState(null, "", nextUrl);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function datasetsForType(catalog: CatalogResponse | undefined, selectedAsset: string, dataType: string): Dataset[] {
  const datasets = catalog?.assets.find((asset) => asset.asset === selectedAsset)?.datasets ?? [];
  return datasets.filter((dataset) => dataset.data_type === dataType);
}

function getPrimaryDatasetForType(datasets: Dataset[]): Dataset | undefined {
  return datasets.find((dataset) => dataset.data_origin === "raw") ?? datasets[0];
}

function getRefreshTargetForType(datasets: Dataset[], dataType: string): Dataset | undefined {
  if (dataType !== "candles") {
    return undefined;
  }
  return datasets.find((dataset) => dataset.data_origin === "raw" && dataset.timeframe === "5m") ?? datasets.find((dataset) => dataset.data_origin === "raw");
}

function datasetStatusTone(dataset: Dataset): "pass" | "warn" | "info" | "idle" {
  if (dataset.quality_status === "updated" || dataset.quality_status === "ingested" || dataset.quality_status === "rebuilt") {
    return "pass";
  }
  if (dataset.quality_status === "blocked" || dataset.quality_status === "failed") {
    return "warn";
  }
  if (dataset.data_origin === "derived") {
    return "info";
  }
  return "idle";
}

function refreshResultText(result: RefreshPlan | undefined): string {
  if (!result) {
    return "No fill action has run for this dataset in this session.";
  }
  if (result.status === "filled") {
    return `Added ${formatNumber(result.rows_added ?? 0)} rows, rebuilt ${formatNumber(result.derived_rebuilt?.length ?? 0)} derived datasets.`;
  }
  if (result.status === "current") {
    return `Current through ${formatTimestamp(result.end_ts ?? null)}.`;
  }
  if (result.status === "no_new_rows") {
    return `No new rows from ${formatTimestamp(result.from_ts ?? null)} to ${formatTimestamp(result.to_ts ?? null)}.`;
  }
  if (result.status === "planned") {
    return `Planned fill from ${formatTimestamp(result.from_ts ?? null)} to ${formatTimestamp(result.to_ts ?? null)}.`;
  }
  return result.reason ?? result.status;
}

function titleize(value: string): string {
  return value
    .split(/[_-]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function DataPage() {
  const { searchParams } = useAppRouter();
  const catalogQuery = useQuery({ queryKey: ["market-data-catalog"], queryFn: fetchMarketDataCatalog });
  const catalog = catalogQuery.data;
  const selectedAsset = getSelectedAsset(catalog, searchParams);
  const selectedDataType = getSelectedDataType(catalog, selectedAsset, searchParams);
  const typeOptions = useMemo(() => getDataTypeOptions(catalog, selectedAsset), [catalog, selectedAsset]);
  const visibleDatasets = useMemo(() => datasetsForType(catalog, selectedAsset, selectedDataType), [catalog, selectedAsset, selectedDataType]);
  const requestedDataset = getSelectedDataset(catalog, selectedAsset, searchParams);
  const selectedDataset = requestedDataset?.asset === selectedAsset && requestedDataset.data_type === selectedDataType ? requestedDataset : getPrimaryDatasetForType(visibleDatasets);
  const refreshTarget = getRefreshTargetForType(visibleDatasets, selectedDataType);

  const candlePreviewQuery = useQuery({
    enabled: Boolean(selectedDataset && selectedDataset.data_type === "candles"),
    queryKey: ["market-data-candles", selectedDataset?.dataset_id],
    queryFn: () => fetchDatasetCandles(selectedDataset!.dataset_id, 25)
  });

  const refreshMutation = useMutation({
    mutationFn: refreshMarketDataDataset,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["market-data-catalog"] });
      void queryClient.invalidateQueries({ queryKey: ["market-data-candles", result.dataset_id] });
    }
  });

  const canRefreshType = Boolean(refreshTarget);
  const selectedRefreshResult = refreshMutation.data?.dataset_id === refreshTarget?.dataset_id ? refreshMutation.data : undefined;
  const selectedRefreshError = refreshMutation.variables === refreshTarget?.dataset_id ? refreshMutation.error : undefined;
  const selectedTypeLabel = typeOptions.find((option) => option.dataType === selectedDataType)?.label ?? titleize(selectedDataType || "data");
  const isRefreshingType = refreshMutation.isPending && refreshMutation.variables === refreshTarget?.dataset_id;

  return (
    <div className="page page--workspace">
      <SplitPane
        left={
          <>
            <div className="list-header">
              <span>Catalog Assets</span>
              <Search aria-hidden="true" />
            </div>
            {catalogQuery.isLoading ? <div className="state-line">Loading local market data coverage...</div> : null}
            {catalogQuery.error ? <div className="state-line state-line--error">{catalogQuery.error.message}</div> : null}
            {catalog?.assets.map((asset) => {
              const dataTypes = new Set(asset.datasets.map((dataset) => dataset.data_type));
              const candleCount = asset.datasets.filter((dataset) => dataset.data_type === "candles").length;
              return (
                <button
                  className={asset.asset === selectedAsset ? "entity-row is-selected" : "entity-row"}
                  key={asset.asset}
                  onClick={() => {
                    const firstType = getDataTypeOptions(catalog, asset.asset)[0]?.dataType ?? "";
                    const firstDataset = getPrimaryDatasetForType(datasetsForType(catalog, asset.asset, firstType));
                    updateDataUrl({ asset: asset.asset, dataType: firstType, dataset: firstDataset?.dataset_id });
                  }}
                  type="button"
                >
                  <strong>{asset.asset}</strong>
                  <span>{dataTypes.size} data types · {candleCount} candle refs</span>
                </button>
              );
            })}
          </>
        }
        leftLabel="Data catalog assets"
        right={
          <>
            <div className="workbench-header">
              <div>
                <span className="eyebrow">Market data</span>
                <h1>{selectedAsset ? `${selectedAsset} Dataset Catalog` : "Canonical Dataset Catalog"}</h1>
              </div>
              <div className="header-actions">
                <StatusBadge tone="info">{catalog ? `${formatNumber(catalog.summary.assets)} assets` : "Catalog"}</StatusBadge>
                <button className="button button--secondary" disabled={catalogQuery.isFetching} onClick={() => void catalogQuery.refetch()} type="button">
                  <RefreshCw aria-hidden="true" />
                  {catalogQuery.isFetching ? "Refreshing" : "Refresh"}
                </button>
              </div>
            </div>

            <div className="filter-strip" aria-label="Dataset type filters">
              {typeOptions.map((option) => (
                <button
                  className={selectedDataType === option.dataType ? "filter-chip is-active" : "filter-chip"}
                  key={option.dataType}
                  onClick={() => {
                    const firstDataset = getPrimaryDatasetForType(datasetsForType(catalog, selectedAsset, option.dataType));
                    updateDataUrl({ dataType: option.dataType, dataset: firstDataset?.dataset_id });
                  }}
                  type="button"
                >
                  {option.label}
                  <span>{option.count}</span>
                </button>
              ))}
            </div>

            <TerminalPanel
              actions={
                selectedDataset ? (
                  <button
                    className="button button--primary"
                    disabled={!canRefreshType || refreshMutation.isPending}
                    onClick={() => refreshTarget && refreshMutation.mutate(refreshTarget.dataset_id)}
                    title={canRefreshType ? `Fill ${selectedTypeLabel.toLowerCase()} to current time` : "Fill is supported for raw candle data only"}
                    type="button"
                  >
                    <UploadCloud aria-hidden="true" />
                    {isRefreshingType ? `Filling ${selectedTypeLabel}` : `Fill ${selectedTypeLabel}`}
                  </button>
                ) : null
              }
              title={`${selectedTypeLabel} Coverage`}
            >
              {isRefreshingType ? (
                <div className="progress-card">
                  <div className="progress-card__header">
                    <strong>Updating {selectedTypeLabel.toLowerCase()}</strong>
                    <span>OKX download + Parquet persist + derived rebuild</span>
                  </div>
                  <div className="progress-rail" aria-label="Data fill in progress">
                    <span />
                  </div>
                  <div className="progress-steps">
                    <span>Fetch raw candles</span>
                    <span>Persist canonical Parquet</span>
                    <span>Rebuild derived candles</span>
                  </div>
                </div>
              ) : null}
              <DataTable
                columns={[
                  { key: "dataset", header: "Dataset", render: (row) => <span className="mono">{row.dataset_id}</span> },
                  { key: "origin", header: "Origin", render: (row) => row.data_origin },
                  { key: "timeframe", header: "TF", render: (row) => row.timeframe ?? "event" },
                  { key: "start", header: "Start", render: (row) => <span className="mono">{formatTimestamp(row.start_ts)}</span> },
                  { key: "end", header: "End", render: (row) => <span className="mono">{formatTimestamp(row.end_ts)}</span> },
                  { key: "rows", header: "Rows", align: "right", render: (row) => formatNumber(row.row_count) },
                  { key: "status", header: "Status", align: "right", render: (row) => <StatusBadge tone={datasetStatusTone(row)}>{row.quality_status}</StatusBadge> }
                ]}
                getRowClassName={(row) => (row.dataset_id === selectedDataset?.dataset_id ? "is-selected" : undefined)}
                getRowKey={(row) => row.dataset_id}
                onRowClick={(row) => updateDataUrl({ asset: row.asset, dataType: row.data_type, dataset: row.dataset_id })}
                rows={visibleDatasets}
              />
            </TerminalPanel>

            <div className="workbench-grid workbench-grid--wide-left">
              <TerminalPanel eyebrow={selectedDataset?.storage_backend ?? "storage"} title="Selected Dataset">
                {selectedDataset ? (
                  <div className="field-grid">
                    <FieldRow label="Asset" value={selectedDataset.asset} />
                    <FieldRow label="Instrument" value={selectedDataset.instrument} />
                    <FieldRow label="Type" value={`${selectedDataset.data_type} / ${selectedDataset.data_origin}`} />
                    <FieldRow label="Timeframe" value={selectedDataset.timeframe ?? "event"} />
                    <FieldRow label="Start UTC" value={formatTimestamp(selectedDataset.start_ts)} />
                    <FieldRow label="End UTC" value={formatTimestamp(selectedDataset.end_ts)} />
                    <FieldRow label="Rows" value={formatNumber(selectedDataset.row_count)} />
                    <FieldRow label="Ingestion" value={selectedDataset.ingestion_version} />
                    <FieldRow label="Source of truth" value={selectedDataset.storage_backend === "parquet" ? "Parquet refs" : selectedDataset.storage_backend} />
                    <FieldRow label="Quality" value={selectedDataset.quality_status} />
                  </div>
                ) : (
                  <div className="state-line">No dataset selected.</div>
                )}
                {selectedDataset ? <div className="storage-uri mono">{selectedDataset.storage_uri}</div> : null}
              </TerminalPanel>

              <TerminalPanel title="Fill Result">
                <div className="state-card">
                  <Database aria-hidden="true" />
                  <span>{selectedRefreshError ? selectedRefreshError.message : refreshResultText(selectedRefreshResult)}</span>
                </div>
                {selectedRefreshResult?.derived_rebuilt?.length ? (
                  <div className="derived-list">
                    {selectedRefreshResult.derived_rebuilt.map((item) => (
                      <div className="field-row" key={item.dataset_id}>
                        <span>{item.timeframe}</span>
                        <strong>{formatNumber(item.row_count)} rows</strong>
                      </div>
                    ))}
                  </div>
                ) : null}
              </TerminalPanel>
            </div>

            <TerminalPanel title="Candle Preview">
              {selectedDataset?.data_type !== "candles" ? <div className="state-line">Preview is available for candle datasets only.</div> : null}
              {candlePreviewQuery.isLoading ? <div className="state-line">Loading candle preview...</div> : null}
              {candlePreviewQuery.error ? <div className="state-line state-line--error">{candlePreviewQuery.error.message}</div> : null}
              {candlePreviewQuery.data ? (
                <DataTable
                  columns={[
                    { key: "timestamp", header: "Timestamp", render: (row) => <span className="mono">{formatTimestamp(String(row.timestamp ?? row.ts ?? ""))}</span> },
                    { key: "open", header: "Open", align: "right", render: (row) => formatCompactValue(row.open) },
                    { key: "high", header: "High", align: "right", render: (row) => formatCompactValue(row.high) },
                    { key: "low", header: "Low", align: "right", render: (row) => formatCompactValue(row.low) },
                    { key: "close", header: "Close", align: "right", render: (row) => formatCompactValue(row.close) },
                    { key: "volume", header: "Volume", align: "right", render: (row) => formatCompactValue(row.volume ?? row.vol) }
                  ]}
                  getRowKey={(row) => String(row.timestamp ?? row.ts ?? JSON.stringify(row))}
                  rows={candlePreviewQuery.data.rows}
                />
              ) : null}
            </TerminalPanel>
          </>
        }
      />
    </div>
  );
}
