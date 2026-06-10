import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { fetchWorkerRuntimeStatus, type RuntimeJob, type WorkerRuntimeStatus } from "../app/api";
import { StatusBadge } from "./StatusBadge";

type WorkerRuntimeNoticeProps = {
  active: boolean;
  job?: RuntimeJob | null;
};

export function WorkerRuntimeNotice({ active, job }: WorkerRuntimeNoticeProps) {
  const runtimeQuery = useQuery({
    enabled: active,
    queryKey: ["worker-runtime-status"],
    queryFn: fetchWorkerRuntimeStatus,
    refetchInterval: active ? 3000 : false
  });
  if (!active) {
    return null;
  }
  const runtime = runtimeQuery.data?.worker_runtime ?? null;
  const state = workerRuntimeState(runtime, runtimeQuery.isLoading, job);
  return (
    <div className={`worker-runtime worker-runtime--${state.tone}`}>
      <Activity aria-hidden="true" />
      <StatusBadge tone={state.badgeTone}>{state.label}</StatusBadge>
      <span>{state.detail}</span>
    </div>
  );
}

function workerRuntimeState(
  runtime: WorkerRuntimeStatus | null,
  loading: boolean,
  job?: RuntimeJob | null
): { label: string; detail: string; tone: "ok" | "warn" | "idle"; badgeTone: "pass" | "warn" | "idle" } {
  const jobStatus = job?.status ?? "queued";
  if (loading && !runtime) {
    return {
      label: "Checking worker",
      detail: `${jobStatus}: waiting for worker status`,
      tone: "idle",
      badgeTone: "idle"
    };
  }
  if (!runtime) {
    return {
      label: "Worker unknown",
      detail: `${jobStatus}: runtime status unavailable`,
      tone: "warn",
      badgeTone: "warn"
    };
  }
  if (runtime.online) {
    return {
      label: "Worker online",
      detail: `${runtime.active_worker_count} active · ${runtime.queued_job_count} queued · ${runtime.running_job_count} running`,
      tone: "ok",
      badgeTone: "pass"
    };
  }
  if (runtime.status === "stale") {
    return {
      label: "Worker stale",
      detail: `${jobStatus}: last worker heartbeat is older than ${runtime.stale_after_seconds}s`,
      tone: "warn",
      badgeTone: "warn"
    };
  }
  return {
    label: "Worker offline",
    detail: `${jobStatus}: start the worker process to claim queued jobs`,
    tone: "warn",
    badgeTone: "warn"
  };
}
