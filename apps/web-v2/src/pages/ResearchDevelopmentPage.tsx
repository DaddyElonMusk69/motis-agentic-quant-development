import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Clipboard, Play, RefreshCw, Trash2, UploadCloud, X } from "lucide-react";
import {
  createStage1Iteration,
  createStage1ResearchSession,
  deleteStage1Iteration,
  deleteStage1ResearchSession,
  fetchDevelopmentQueue,
  fetchStage0UniverseRuns,
  fetchStage1AgentPrompt,
  fetchStage1Gate,
  fetchStage1IterationDetail,
  fetchStage1Iterations,
  fetchStage1ResearchSessions,
  generateStage1FailureAudit,
  promoteExecutionBundle,
  promoteStage2ExitPolicy,
  runStage1CanonicalReadout,
  runStage2CaptureCurve,
  runStage3ExactProtection,
  runStage3FixedSl,
  runStage3LocalVariants,
  runStage3Pyramid,
  runStage4RealizedExpectancy,
  scoreStage1Iteration,
  type DevelopmentQueueRow,
  type ResearchStageId,
  type Stage0UniverseRun,
  type Stage1AgentPrompt,
  type Stage1GateSummary,
  type Stage1IterationDetail,
  type Stage1IterationSummary,
  type Stage1ResearchSession,
  type Stage1SampleMethod,
  type Stage1SampleRole,
  type Stage1SeedStrategyPreference,
  type Stage1TrainingScore,
  type Stage2CaptureRate
} from "../app/api";
import { formatNumber } from "../app/format";
import { queryClient } from "../app/queryClient";
import { useAppRouter } from "../app/router";
import { DataTable } from "../components/DataTable";
import { FieldRow } from "../components/FieldRow";
import { SplitPane } from "../components/SplitPane";
import { StatusBadge } from "../components/StatusBadge";
import { TerminalPanel } from "../components/TerminalPanel";

type Stage1EvidenceMode = {
  title: string;
  tone: "pass" | "warn" | "info" | "idle";
  allowedEvidence: string;
  agentUse: string;
  nextAction: string;
};

type Stage1OverrideAction =
  | { kind: "create_walk_forward_bundle"; title: string; body: string; confirmLabel: string }
  | { kind: "run_canonical_stage1a"; title: string; body: string; confirmLabel: string };

type Stage1StartChoice = {
  strategyId: string;
  latestAvailable: boolean;
  latestLabel: string;
};

const stage1Roles: Stage1SampleRole[] = ["training", "walk_forward_test"];

function updateDevelopmentUrl(next: { pool?: string; candidate?: string; stage?: ResearchStageId }) {
  const params = new URLSearchParams(window.location.search);
  if (next.pool !== undefined) {
    params.set("pool", next.pool);
  }
  if (next.candidate !== undefined) {
    params.set("candidate", next.candidate);
  }
  if (next.stage !== undefined) {
    params.set("stage", next.stage);
  }
  const query = params.toString();
  const nextUrl = `/research/development${query ? `?${query}` : ""}`;
  if (`${window.location.pathname}${window.location.search}` === nextUrl) {
    return;
  }
  window.history.pushState(null, "", nextUrl);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function selectedPool(runs: Stage0UniverseRun[] | undefined, searchParams: URLSearchParams): Stage0UniverseRun | undefined {
  const requested = searchParams.get("pool");
  return runs?.find((run) => run.universe_run_id === requested) ?? runs?.[0];
}

function selectedCandidate(rows: DevelopmentQueueRow[], searchParams: URLSearchParams): DevelopmentQueueRow | undefined {
  const requested = searchParams.get("candidate");
  return rows.find((row) => row.candidate_id === requested) ?? rows[0];
}

function shortPoolId(value: string): string {
  return value.replace("stage0-universe-", "").replace("training-pool-", "");
}

function dateOnly(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : "n/a";
}

function stageWindows(run: Stage0UniverseRun | undefined): {
  trainStart: string;
  trainEnd: string;
  walkForwardStart: string;
  walkForwardEnd: string;
} {
  return {
    trainStart: dateOnly(run?.train_start ?? run?.window_start),
    trainEnd: dateOnly(run?.train_end),
    walkForwardStart: dateOnly(run?.walk_forward_start),
    walkForwardEnd: dateOnly(run?.walk_forward_end ?? run?.window_end)
  };
}

function splitWindowLine(run: Stage0UniverseRun | undefined): string {
  const windows = stageWindows(run);
  return `Train ${windows.trainStart} - ${windows.trainEnd} · Walk-forward ${windows.walkForwardStart} - ${windows.walkForwardEnd}`;
}

function actionType(row: DevelopmentQueueRow | undefined): string {
  const nextAction = row?.next_action as { action_type?: string; type?: string } | undefined;
  return nextAction?.action_type ?? nextAction?.type ?? "";
}

function stageTone(row: DevelopmentQueueRow): "pass" | "warn" | "info" | "idle" {
  if (["stage4_complete", "stage3_complete", "stage3_grid_complete", "stage2_policy_promoted", "stage2_complete", "stage1_frozen"].includes(row.development_status)) {
    return "pass";
  }
  if (["stage1_in_progress", "stage1_ready_to_freeze"].includes(row.development_status)) {
    return "info";
  }
  if (row.stage0_status !== "accepted") {
    return "warn";
  }
  return "idle";
}

function developmentLabel(row: DevelopmentQueueRow | undefined): string {
  if (!row) {
    return "No candidate";
  }
  const labels: Record<string, string> = {
    stage1_not_started: "Ready for Stage 1",
    stage1_in_progress: "Stage 1 in progress",
    stage1_ready_to_freeze: "Ready to freeze",
    stage1_frozen: "Stage 2 ready",
    stage2_complete: "Exit policy ready",
    stage2_policy_promoted: "Stage 3 ready",
    stage3_grid_complete: "Pyramid ready",
    stage3_complete: "Stage 4 ready",
    stage4_complete: "Promotion review"
  };
  return labels[row.development_status] ?? row.development_status.replaceAll("_", " ");
}

function normalizeResearchStage(value: string | null | undefined): ResearchStageId {
  if (value?.startsWith("stage2")) {
    return "stage2";
  }
  if (value?.startsWith("stage3")) {
    return "stage3";
  }
  if (value?.startsWith("stage4")) {
    return "stage4";
  }
  return "stage1";
}

function stage1RoleForIteration(iteration: Pick<Stage1IterationSummary, "sample_method">): Stage1SampleRole {
  return iteration.sample_method === "walk_forward_test" ? "walk_forward_test" : "training";
}

function stage1BundleRoleForMethod(method: Stage1SampleMethod): "strategy_builder" | "evaluator" {
  return method === "training" ? "strategy_builder" : "evaluator";
}

function stage1RoleLabel(role: Stage1SampleRole): string {
  return role === "walk_forward_test" ? "Walk-forward" : "Training";
}

function stage1BundleLabel(iteration: Stage1IterationSummary): string {
  return iteration.bundle_role === "strategy_builder" ? "Builder" : "Evaluator";
}

function stage1ScoreForRole(iteration: Stage1IterationSummary, role: Stage1SampleRole): Stage1TrainingScore | null {
  if (role === "training") {
    return iteration.scores?.training ?? iteration.training_score ?? null;
  }
  return iteration.scores?.[role] ?? null;
}

function stage1Agreement(value: number | undefined): string {
  return `${((value ?? 0) * 100).toFixed(2)}%`;
}

function formatUtcTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("en-US", {
    timeZone: "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).replace(",", "") + " UTC";
}

function roleIterations(iterations: Stage1IterationSummary[]): Record<Stage1SampleRole, Stage1IterationSummary[]> {
  return {
    training: iterations.filter((iteration) => stage1RoleForIteration(iteration) === "training"),
    walk_forward_test: iterations.filter((iteration) => stage1RoleForIteration(iteration) === "walk_forward_test")
  };
}

function gateScore(gate: Stage1GateSummary | null, role: Stage1SampleRole): string {
  const score = gate?.roles[role]?.score;
  return score ? stage1Agreement(score.metrics.directional_agreement) : "n/a";
}

function evidenceMode(gate: Stage1GateSummary | null, session: Stage1ResearchSession | null): Stage1EvidenceMode {
  if (!session) {
    return {
      title: "Not started",
      tone: "idle",
      allowedEvidence: "None yet",
      agentUse: "Start Stage 1",
      nextAction: "Create candidate workspace"
    };
  }
  if (gate?.stage4_realized_expectancy.exists) {
    return {
      title: "Promotion evidence ready",
      tone: "pass",
      allowedEvidence: "Frozen Stage 1, Stage 2-4 artifacts",
      agentUse: "Review only",
      nextAction: "Promote or rerun a new pool"
    };
  }
  if (gate?.canonical_readout.exists) {
    return {
      title: "Stage 1 frozen",
      tone: "pass",
      allowedEvidence: "Canonical decision set",
      agentUse: "No same-cycle edits",
      nextAction: "Run downstream stages"
    };
  }
  const trainingStatus = gate?.roles.training?.status ?? "missing";
  const walkForwardStatus = gate?.roles.walk_forward_test?.status ?? "missing";
  if (walkForwardStatus === "fail") {
    return {
      title: "Walk-forward failed",
      tone: "warn",
      allowedEvidence: "Walk-forward postmortem only",
      agentUse: "No tuning on test data",
      nextAction: "Audit, then start a new pool"
    };
  }
  if (trainingStatus === "pass") {
    return {
      title: "Walk-forward gate",
      tone: "info",
      allowedEvidence: "Training is fixed; test is evaluator-only",
      agentUse: "Score or postmortem",
      nextAction: gate?.ready_to_freeze ? "Freeze Stage 1" : "Create/score walk-forward"
    };
  }
  return {
    title: "Training iteration",
    tone: trainingStatus === "fail" ? "warn" : "info",
    allowedEvidence: "Training labels and packets",
    agentUse: "Can edit strategy script",
    nextAction: trainingStatus === "fail" ? "Audit and iterate" : "Create/score training"
  };
}

function formatCaptureRate(value: Stage2CaptureRate | undefined): string {
  if (!value) {
    return "-";
  }
  return `${value.rate.toFixed(1)}% (${formatNumber(value.reached)}/${formatNumber(value.total)})`;
}

function formatPct(value: number | undefined | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(1)}%`;
}

function formatDecimal(value: number | undefined | null, digits = 2): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function shortId(value: string | undefined | null): string {
  if (!value) {
    return "-";
  }
  return value.length > 26 ? `${value.slice(0, 23)}...` : value;
}

function formatRangeList(values: number[] | undefined): string {
  if (!values?.length) {
    return "-";
  }
  if (values.length <= 4) {
    return values.map((value) => formatPct(value)).join(", ");
  }
  return `${formatPct(values[0])} - ${formatPct(values[values.length - 1])} (${formatNumber(values.length)})`;
}

function formatUsd(value: number | undefined | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function scoreExists(gate: Stage1GateSummary | null, role: Stage1SampleRole): boolean {
  return Boolean(gate?.roles[role]?.score);
}

function invalidateDevelopment(sessionId?: string, poolId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["stage1-sessions"] });
  if (sessionId) {
    void queryClient.invalidateQueries({ queryKey: ["stage1-iterations", sessionId] });
    void queryClient.invalidateQueries({ queryKey: ["stage1-gate", sessionId] });
  }
  if (poolId) {
    void queryClient.invalidateQueries({ queryKey: ["development-queue", poolId] });
  }
}

export function ResearchDevelopmentPage() {
  const { searchParams } = useAppRouter();
  const [prompt, setPrompt] = useState<Stage1AgentPrompt | null>(null);
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [overrideAction, setOverrideAction] = useState<Stage1OverrideAction | null>(null);
  const [selectedIteration, setSelectedIteration] = useState<Stage1IterationSummary | null>(null);
  const [startChoice, setStartChoice] = useState<Stage1StartChoice | null>(null);
  const [stage4Inputs, setStage4Inputs] = useState({
    initial_capital_usdt: 10000,
    margin_allocation_pct: 30,
    leverage: 5
  });

  const poolQuery = useQuery({ queryKey: ["stage0-universe-runs"], queryFn: fetchStage0UniverseRuns });
  const pool = selectedPool(poolQuery.data?.runs, searchParams);
  const queueQuery = useQuery({
    enabled: Boolean(pool?.universe_run_id),
    queryKey: ["development-queue", pool?.universe_run_id],
    queryFn: () => fetchDevelopmentQueue(pool!.universe_run_id)
  });
  const sessionsQuery = useQuery({ queryKey: ["stage1-sessions"], queryFn: fetchStage1ResearchSessions });

  const acceptedRows = useMemo(
    () => (queueQuery.data?.queue ?? []).filter((row) => row.stage0_status === "accepted"),
    [queueQuery.data?.queue]
  );
  const row = selectedCandidate(acceptedRows, searchParams);
  const session = useMemo(() => {
    return sessionsQuery.data?.sessions.find((item) => item.session_id === row?.stage1_session_id)
      ?? sessionsQuery.data?.sessions.find((item) => item.source_candidate_id === row?.candidate_id)
      ?? null;
  }, [row?.candidate_id, row?.stage1_session_id, sessionsQuery.data?.sessions]);
  const activeStage = normalizeResearchStage(searchParams.get("stage") ?? row?.current_stage);

  const iterationsQuery = useQuery({
    enabled: Boolean(session?.session_id),
    queryKey: ["stage1-iterations", session?.session_id],
    queryFn: () => fetchStage1Iterations(session!.session_id)
  });
  const gateQuery = useQuery({
    enabled: Boolean(session?.session_id),
    queryKey: ["stage1-gate", session?.session_id],
    queryFn: () => fetchStage1Gate(session!.session_id)
  });
  const iterationDetailQuery = useQuery({
    enabled: Boolean(session?.session_id && selectedIteration?.iteration_id),
    queryKey: ["stage1-iteration-detail", session?.session_id, selectedIteration?.iteration_id],
    queryFn: () => fetchStage1IterationDetail({ session_id: session!.session_id, iteration_id: selectedIteration!.iteration_id })
  });

  const gate = gateQuery.data?.gate ?? row?.stage1_gate ?? null;
  const iterations = iterationsQuery.data?.iterations ?? [];
  const groupedIterations = useMemo(() => roleIterations(iterations), [iterations]);
  const mode = evidenceMode(gate, session);
  const canCreateWalkForward = scoreExists(gate, "training");
  const canForceWalkForward = canCreateWalkForward && gate?.roles.training?.status === "fail";
  const canForceFreeze = scoreExists(gate, "training") && scoreExists(gate, "walk_forward_test") && !gate?.ready_to_freeze;
  const plannedStrategyId = row ? (row.strategy_id ?? `${row.asset.toLowerCase()}-${row.signal_engine_id}-strategy-v01`) : "";
  const latestSeedSession = useMemo(() => {
    if (!row) {
      return null;
    }
    return (sessionsQuery.data?.sessions ?? []).find(
      (item) =>
        item.asset === row.asset &&
        item.signal_engine_id === row.signal_engine_id &&
        item.strategy_id === plannedStrategyId &&
        item.session_id !== session?.session_id
    ) ?? null;
  }, [plannedStrategyId, row, session?.session_id, sessionsQuery.data?.sessions]);

  const createSessionMutation = useMutation({
    mutationFn: createStage1ResearchSession,
    onSuccess: (result) => {
      invalidateDevelopment(result.session.session_id, pool?.universe_run_id);
    }
  });
  const createIterationMutation = useMutation({
    mutationFn: createStage1Iteration,
    onSuccess: (_result, variables) => invalidateDevelopment(variables.session_id, pool?.universe_run_id)
  });
  const deleteIterationMutation = useMutation({
    mutationFn: deleteStage1Iteration,
    onSuccess: (_result, variables) => invalidateDevelopment(variables.session_id, pool?.universe_run_id)
  });
  const deleteSessionMutation = useMutation({
    mutationFn: deleteStage1ResearchSession,
    onSuccess: (_result, sessionId) => {
      setPrompt(null);
      setSelectedIteration(null);
      invalidateDevelopment(sessionId, pool?.universe_run_id);
    }
  });
  const promptMutation = useMutation({
    mutationFn: fetchStage1AgentPrompt,
    onSuccess: (result) => {
      setCopiedPrompt(false);
      setPrompt(result);
    }
  });
  const scoreMutation = useMutation({
    mutationFn: scoreStage1Iteration,
    onSuccess: (_result, variables) => invalidateDevelopment(variables.session_id, pool?.universe_run_id)
  });
  const auditMutation = useMutation({
    mutationFn: generateStage1FailureAudit,
    onSuccess: (_result, variables) => invalidateDevelopment(variables.session_id, pool?.universe_run_id)
  });
  const canonicalMutation = useMutation({
    mutationFn: runStage1CanonicalReadout,
    onSuccess: (_result, variables) => invalidateDevelopment(variables.session_id, pool?.universe_run_id)
  });
  const stage2Mutation = useMutation({
    mutationFn: runStage2CaptureCurve,
    onSuccess: (_result, sessionId) => invalidateDevelopment(sessionId, pool?.universe_run_id)
  });
  const stage2ExitPolicyMutation = useMutation({
    mutationFn: promoteStage2ExitPolicy,
    onSuccess: (_result, variables) => invalidateDevelopment(variables.session_id, pool?.universe_run_id)
  });
  const stage3FixedSlMutation = useMutation({
    mutationFn: runStage3FixedSl,
    onSuccess: (_result, sessionId) => invalidateDevelopment(sessionId, pool?.universe_run_id)
  });
  const stage3ExactProtectionMutation = useMutation({
    mutationFn: runStage3ExactProtection,
    onSuccess: (_result, sessionId) => invalidateDevelopment(sessionId, pool?.universe_run_id)
  });
  const stage3LocalVariantsMutation = useMutation({
    mutationFn: runStage3LocalVariants,
    onSuccess: (_result, sessionId) => invalidateDevelopment(sessionId, pool?.universe_run_id)
  });
  const stage3PyramidMutation = useMutation({
    mutationFn: runStage3Pyramid,
    onSuccess: (_result, sessionId) => invalidateDevelopment(sessionId, pool?.universe_run_id)
  });
  const stage4Mutation = useMutation({
    mutationFn: runStage4RealizedExpectancy,
    onSuccess: (_result, variables) => invalidateDevelopment(variables.session_id, pool?.universe_run_id)
  });
  const promoteMutation = useMutation({
    mutationFn: promoteExecutionBundle,
    onSuccess: (_result, sessionId) => invalidateDevelopment(sessionId, pool?.universe_run_id)
  });

  useEffect(() => {
    if (!searchParams.get("pool") && pool?.universe_run_id) {
      updateDevelopmentUrl({ pool: pool.universe_run_id });
    }
  }, [pool?.universe_run_id, searchParams]);

  useEffect(() => {
    if (!searchParams.get("candidate") && row?.candidate_id) {
      updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage: activeStage });
    }
  }, [activeStage, row?.candidate_id, row?.universe_run_id, searchParams]);

  useEffect(() => {
    setSelectedIteration(null);
  }, [session?.session_id]);

  const startStage1 = (seedPreference: Stage1SeedStrategyPreference) => {
    if (!row || !pool) {
      return;
    }
    const windows = stageWindows(pool);
    createSessionMutation.mutate({
      source_candidate_id: row.candidate_id,
      strategy_id: plannedStrategyId,
      strategy_version: "v0.1",
      train_start: windows.trainStart,
      train_end: windows.trainEnd,
      walk_forward_start: windows.walkForwardStart,
      walk_forward_end: windows.walkForwardEnd,
      seed_strategy_preference: seedPreference
    });
  };

  const requestStartStage1 = () => {
    if (!row) {
      return;
    }
    setStartChoice({
      strategyId: plannedStrategyId,
      latestAvailable: Boolean(latestSeedSession),
      latestLabel: latestSeedSession
        ? `${latestSeedSession.strategy_version} · ${latestSeedSession.seed_strategy_source_type ?? "latest"}`
        : "No prior developed strategy for this pair",
    });
  };

  const createBundle = (role: Stage1SampleMethod) => {
    if (!session) {
      return;
    }
    createIterationMutation.mutate({
      session_id: session.session_id,
      sample_method: role,
      bundle_role: stage1BundleRoleForMethod(role)
    });
  };

  const runStage4 = () => {
    if (!session) {
      return;
    }
    stage4Mutation.mutate({
      session_id: session.session_id,
      ...stage4Inputs
    });
  };

  const requestCreateBundle = (role: Stage1SampleMethod) => {
    if (role === "walk_forward_test" && canForceWalkForward) {
      setOverrideAction({
        kind: "create_walk_forward_bundle",
        title: "Proceed to Walk-Forward?",
        body: "Training is below the 55% Stage 1 threshold. You can still create and score the walk-forward bundle to inspect how the pair behaves out of sample.",
        confirmLabel: "Create Walk-Forward Bundle",
      });
      return;
    }
    createBundle(role);
  };

  const requestCanonicalFreeze = (force = false) => {
    if (!session) {
      return;
    }
    if (!force && canForceFreeze) {
      setOverrideAction({
        kind: "run_canonical_stage1a",
        title: "Freeze Below Gate?",
        body: "Training and walk-forward have both been scored, but at least one slice is below the 55% threshold. You can still freeze the canonical Stage 1 set and continue into downstream stages.",
        confirmLabel: "Freeze Anyway",
      });
      return;
    }
    canonicalMutation.mutate({ session_id: session.session_id, force });
  };

  const runNextAction = () => {
    const type = actionType(row);
    if (!row) {
      return;
    }
    if (type === "start_stage1") {
      requestStartStage1();
      return;
    }
    if (!session) {
      return;
    }
    if (type === "create_training_bundle") {
      createBundle("training");
    } else if (type === "create_walk_forward_bundle") {
      requestCreateBundle("walk_forward_test");
    } else if (type === "run_canonical_stage1a") {
      requestCanonicalFreeze();
    } else if (type === "run_stage2_capture_curve") {
      updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage: "stage2" });
      stage2Mutation.mutate(session.session_id);
    } else if (type === "run_stage3_fixed_sl") {
      updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage: "stage3" });
      stage3FixedSlMutation.mutate(session.session_id);
    } else if (type === "run_stage3_exact_protection") {
      updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage: "stage3" });
      stage3ExactProtectionMutation.mutate(session.session_id);
    } else if (type === "run_stage3_local_variants" || type === "run_stage3_grid_search") {
      updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage: "stage3" });
      stage3LocalVariantsMutation.mutate(session.session_id);
    } else if (type === "run_stage3_pyramid") {
      updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage: "stage3" });
      stage3PyramidMutation.mutate(session.session_id);
    } else if (type === "run_stage4_realized_expectancy") {
      updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage: "stage4" });
      runStage4();
    }
  };

  const stage1PrimaryAction = (() => {
    if (!row) {
      return { label: "Select Candidate", disabled: true, run: () => undefined };
    }
    if (!session) {
      return {
        label: createSessionMutation.isPending ? "Starting" : "Start Stage 1",
        disabled: createSessionMutation.isPending,
        run: requestStartStage1,
      };
    }
    if (!scoreExists(gate, "training")) {
      return {
        label: createIterationMutation.isPending ? "Creating" : "Create Training Bundle",
        disabled: createIterationMutation.isPending,
        run: () => createBundle("training"),
      };
    }
    if (!scoreExists(gate, "walk_forward_test")) {
      return {
        label: createIterationMutation.isPending ? "Creating" : "Create Walk-Forward Bundle",
        disabled: createIterationMutation.isPending || !canCreateWalkForward,
        run: () => requestCreateBundle("walk_forward_test"),
      };
    }
    if (!gate?.canonical_readout.exists) {
      return {
        label: canonicalMutation.isPending ? "Freezing" : "Freeze Stage 1",
        disabled: canonicalMutation.isPending,
        run: () => requestCanonicalFreeze(),
      };
    }
    return {
      label: row.next_action.label ?? "Ready",
      disabled: Boolean(row.next_action.disabled),
      run: runNextAction,
    };
  })();

  const visibleErrors = [
    poolQuery.error,
    queueQuery.error,
    sessionsQuery.error,
    iterationsQuery.error,
    gateQuery.error,
    iterationDetailQuery.error,
    createSessionMutation.error,
    createIterationMutation.error,
    deleteIterationMutation.error,
    deleteSessionMutation.error,
    promptMutation.error,
    scoreMutation.error,
    auditMutation.error,
    canonicalMutation.error,
    stage2Mutation.error,
    stage2ExitPolicyMutation.error,
    stage3FixedSlMutation.error,
    stage3ExactProtectionMutation.error,
    stage3LocalVariantsMutation.error,
    stage3PyramidMutation.error,
    stage4Mutation.error,
    promoteMutation.error
  ].filter(Boolean) as Error[];

  return (
    <div className="page page--workspace">
      <SplitPane
        className="split-pane--wide-list"
        workbenchClassName="development-workbench"
        left={
          <>
            <div className="list-header">
              <span>Development</span>
              <button className="icon-button" disabled={queueQuery.isFetching} onClick={() => void queueQuery.refetch()} type="button" aria-label="Refresh development queue">
                <RefreshCw aria-hidden="true" />
              </button>
            </div>
            <label className="compact-select">
              Training Pool
              <select value={pool?.universe_run_id ?? ""} onChange={(event) => updateDevelopmentUrl({ pool: event.target.value })}>
                {(poolQuery.data?.runs ?? []).map((run) => (
                  <option value={run.universe_run_id} key={run.universe_run_id}>{shortPoolId(run.universe_run_id)}</option>
                ))}
              </select>
            </label>
            <div className="state-line">
              <strong>{pool ? shortPoolId(pool.universe_run_id) : "No pool"}</strong>
              <span>{splitWindowLine(pool)}</span>
            </div>
            {queueQuery.isLoading || sessionsQuery.isLoading ? <div className="state-line">Loading development queue...</div> : null}
            {acceptedRows.length === 0 && !queueQuery.isLoading ? <div className="state-line">No accepted candidates in this training pool.</div> : null}
            <div className="development-candidate-list">
              {acceptedRows.map((candidate) => (
                <button
                  className={candidate.candidate_id === row?.candidate_id ? "development-candidate-card is-selected" : "development-candidate-card"}
                  key={candidate.candidate_id}
                  onClick={() => updateDevelopmentUrl({ pool: candidate.universe_run_id, candidate: candidate.candidate_id, stage: normalizeResearchStage(candidate.current_stage) })}
                  type="button"
                >
                  <div className="signal-pool-card__top">
                    <strong>{candidate.asset}</strong>
                    <StatusBadge tone={stageTone(candidate)}>{developmentLabel(candidate)}</StatusBadge>
                  </div>
                  <span>{candidate.signal_engine_id} · {candidate.strategy_id ?? "base strategy"}</span>
                  <small>Trigger {candidate.trigger_rate_pct === null ? "n/a" : `${candidate.trigger_rate_pct}%`} · {formatNumber(candidate.stage0_evaluated_signal_count ?? candidate.packet_count)} signals</small>
                  <small>{candidate.next_action.label}</small>
                </button>
              ))}
            </div>
          </>
        }
        right={
          <>
            <div className="workbench-header development-header">
              <div>
                <span className="eyebrow">Candidate workbench</span>
                <h1>{row ? `${row.asset} / ${row.signal_engine_id}` : "Select a candidate"}</h1>
              </div>
              <div className="header-actions">
                {row ? <StatusBadge tone={stageTone(row)}>{developmentLabel(row)}</StatusBadge> : null}
                <button
                  className="button button--primary"
                  disabled={activeStage === "stage1" ? stage1PrimaryAction.disabled : (!row || Boolean(row.next_action.disabled) || createSessionMutation.isPending || createIterationMutation.isPending)}
                  onClick={activeStage === "stage1" ? stage1PrimaryAction.run : runNextAction}
                  type="button"
                >
                  <Play aria-hidden="true" />
                  {activeStage === "stage1" ? stage1PrimaryAction.label : row?.next_action.label ?? "Select Candidate"}
                </button>
              </div>
            </div>

            {visibleErrors.map((error) => <div className="state-line state-line--error" key={error.message}>{error.message}</div>)}

            <div className="development-summary-strip">
              <div>
                <span>Pool</span>
                <strong>{pool ? shortPoolId(pool.universe_run_id) : "n/a"}</strong>
              </div>
              <div>
                <span>Windows</span>
                <strong>{splitWindowLine(pool)}</strong>
              </div>
              <div>
                <span>Strategy</span>
                <strong>{session ? `${session.strategy_id} @ ${session.strategy_version}` : row?.strategy_id ?? "not started"}</strong>
              </div>
              <div>
                <span>Blocker</span>
                <strong className={gate?.blockers.length ? "tone-risk" : "tone-pass"}>{gate?.blockers[0] ?? (session ? "none" : "Stage 1 not started")}</strong>
              </div>
            </div>

            <StageTabs
              activeStage={activeStage}
              gate={gate}
              row={row}
              onStageChange={(stage) => row && updateDevelopmentUrl({ pool: row.universe_run_id, candidate: row.candidate_id, stage })}
            />

            {activeStage === "stage1" ? (
              <Stage1Panel
                createBundlePending={createIterationMutation.isPending}
                gate={gate}
                groupedIterations={groupedIterations}
                iterations={iterations}
                loadingIterations={iterationsQuery.isLoading}
                mode={mode}
                onCreateBundle={requestCreateBundle}
                onAudit={(iteration) => auditMutation.mutate({ session_id: session!.session_id, iteration_id: iteration.iteration_id, sample_role: stage1RoleForIteration(iteration) })}
                onDelete={(iteration) => deleteIterationMutation.mutate({ session_id: session!.session_id, iteration_id: iteration.iteration_id })}
                onOpenIteration={setSelectedIteration}
                onOpenPrompt={(iteration) => promptMutation.mutate({ session_id: session!.session_id, iteration_id: iteration.iteration_id })}
                onRunCanonical={() => requestCanonicalFreeze()}
                onResetSession={() => session && deleteSessionMutation.mutate(session.session_id)}
                onScore={(iteration) => scoreMutation.mutate({ session_id: session!.session_id, iteration_id: iteration.iteration_id, sample_role: stage1RoleForIteration(iteration) })}
                onStartStage1={requestStartStage1}
                row={row}
                runningCanonical={canonicalMutation.isPending}
                session={session}
                startingSession={createSessionMutation.isPending}
              />
            ) : null}

            {activeStage === "stage2" ? (
              <Stage2Panel
                gate={gate}
                onPromotePolicy={(policy) => session && stage2ExitPolicyMutation.mutate({ session_id: session.session_id, ...policy })}
                onRun={() => session && stage2Mutation.mutate(session.session_id)}
                promotingPolicy={stage2ExitPolicyMutation.isPending}
                running={stage2Mutation.isPending}
              />
            ) : null}

            {activeStage === "stage3" ? (
              <Stage3Panel
                gate={gate}
                onRunExactProtection={() => session && stage3ExactProtectionMutation.mutate(session.session_id)}
                onRunFixedSl={() => session && stage3FixedSlMutation.mutate(session.session_id)}
                onRunLocalVariants={() => session && stage3LocalVariantsMutation.mutate(session.session_id)}
                onRunPyramid={() => session && stage3PyramidMutation.mutate(session.session_id)}
                exactProtectionRunning={stage3ExactProtectionMutation.isPending}
                fixedSlRunning={stage3FixedSlMutation.isPending}
                localVariantsRunning={stage3LocalVariantsMutation.isPending}
                pyramidRunning={stage3PyramidMutation.isPending}
              />
            ) : null}

            {activeStage === "stage4" ? (
              <Stage4Panel
                gate={gate}
                onPromote={() => session && promoteMutation.mutate(session.session_id)}
                onRun={runStage4}
                inputs={stage4Inputs}
                onInputsChange={setStage4Inputs}
                promoting={promoteMutation.isPending}
                running={stage4Mutation.isPending}
              />
            ) : null}
          </>
        }
      />

      {startChoice ? (
        <div className="modal-backdrop" role="presentation">
          <section className="terminal-modal stage1-start-modal" role="dialog" aria-modal="true" aria-labelledby="stage1-start-title">
            <header className="terminal-modal__header">
              <div>
                <span className="eyebrow">Start Stage 1</span>
                <h2 id="stage1-start-title">Choose Base Strategy</h2>
              </div>
              <button className="icon-button" onClick={() => setStartChoice(null)} type="button" aria-label="Close start stage 1 dialog">
                <X aria-hidden="true" />
              </button>
            </header>
            <div className="terminal-modal__body">
              <div className="stage1-start-grid">
                <button className="stage1-start-option" onClick={() => { setStartChoice(null); startStage1("engine_base"); }} type="button">
                  <strong>Base Strategy Template</strong>
                  <span>Use the signal engine’s deterministic base script.</span>
                </button>
                <button
                  className={startChoice.latestAvailable ? "stage1-start-option" : "stage1-start-option is-disabled"}
                  disabled={!startChoice.latestAvailable}
                  onClick={() => { setStartChoice(null); startStage1("latest_pair"); }}
                  type="button"
                >
                  <strong>Latest Developed Strategy</strong>
                  <span>{startChoice.latestLabel}</span>
                </button>
              </div>
            </div>
            <footer className="terminal-modal__footer">
              <span>{startChoice.strategyId}</span>
              <button className="button button--secondary" onClick={() => setStartChoice(null)} type="button">Cancel</button>
            </footer>
          </section>
        </div>
      ) : null}

      {overrideAction ? (
        <div className="modal-backdrop" role="presentation">
          <section className="terminal-modal stage1-override-modal" role="dialog" aria-modal="true" aria-labelledby="stage1-override-title">
            <header className="terminal-modal__header">
              <div>
                <span className="eyebrow">Override Gate</span>
                <h2 id="stage1-override-title">{overrideAction.title}</h2>
              </div>
              <button className="icon-button" onClick={() => setOverrideAction(null)} type="button" aria-label="Close override dialog">
                <X aria-hidden="true" />
              </button>
            </header>
            <div className="terminal-modal__body">
              <p className="modal-copy">{overrideAction.body}</p>
            </div>
            <footer className="terminal-modal__footer">
              <span>The current cycle stays auditable. This only removes the UI hard stop.</span>
              <div className="table-action-row">
                <button className="button button--secondary" onClick={() => setOverrideAction(null)} type="button">Cancel</button>
                <button
                  className="button button--primary"
                  onClick={() => {
                    const action = overrideAction;
                    setOverrideAction(null);
                    if (action.kind === "create_walk_forward_bundle") {
                      createBundle("walk_forward_test");
                    } else if (action.kind === "run_canonical_stage1a") {
                      requestCanonicalFreeze(true);
                    }
                  }}
                  type="button"
                >
                  <Play aria-hidden="true" />
                  {overrideAction.confirmLabel}
                </button>
              </div>
            </footer>
          </section>
        </div>
      ) : null}

      {selectedIteration ? (
        <div className="modal-backdrop" role="presentation">
          <section className="terminal-modal iteration-detail-modal" role="dialog" aria-modal="true" aria-labelledby="iteration-detail-title">
            <header className="terminal-modal__header">
              <div>
                <span className="eyebrow">Iteration Detail</span>
                <h2 id="iteration-detail-title">{selectedIteration.iteration_id}</h2>
              </div>
              <button className="icon-button" onClick={() => setSelectedIteration(null)} type="button" aria-label="Close iteration details">
                <X aria-hidden="true" />
              </button>
            </header>
            <div className="terminal-modal__body">
              {iterationDetailQuery.isLoading ? <div className="state-line">Loading iteration detail...</div> : null}
              {iterationDetailQuery.error ? <div className="state-line state-line--error">{iterationDetailQuery.error.message}</div> : null}
              {iterationDetailQuery.data?.detail ? <IterationDetailPanel detail={iterationDetailQuery.data.detail} /> : null}
            </div>
            <footer className="terminal-modal__footer">
              <span>Review the full signal ledger before auditing or spawning the next bundle.</span>
              <button className="button button--secondary" onClick={() => setSelectedIteration(null)} type="button">Close</button>
            </footer>
          </section>
        </div>
      ) : null}

      {prompt ? (
        <div className="modal-backdrop" role="presentation">
          <section className="terminal-modal prompt-terminal-modal" role="dialog" aria-modal="true" aria-labelledby="agent-prompt-title">
            <header className="terminal-modal__header">
              <div>
                <span className="eyebrow">{prompt.prompt_type}</span>
                <h2 id="agent-prompt-title">{prompt.iteration_id}</h2>
              </div>
              <button className="icon-button" onClick={() => setPrompt(null)} type="button" aria-label="Close agent prompt">
                <X aria-hidden="true" />
              </button>
            </header>
            <div className="terminal-modal__body">
              <div className="field-stack">
                <FieldRow label="Prompt path" value={prompt.prompt_path} />
                <pre className="agent-prompt-box">{prompt.prompt}</pre>
              </div>
            </div>
            <footer className="terminal-modal__footer">
              <span>{copiedPrompt ? "Copied to clipboard" : "Copy this prompt into the local agent session."}</span>
              <button
                className="button button--primary"
                onClick={() => {
                  void navigator.clipboard.writeText(prompt.prompt).then(() => setCopiedPrompt(true));
                }}
                type="button"
              >
                <Clipboard aria-hidden="true" />
                Copy Prompt
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  );
}

function StageTabs({
  activeStage,
  gate,
  onStageChange,
  row
}: {
  activeStage: ResearchStageId;
  gate: Stage1GateSummary | null;
  onStageChange: (stage: ResearchStageId) => void;
  row: DevelopmentQueueRow | undefined;
}) {
  const stages: Array<{ id: ResearchStageId; label: string; state: string; tone: "pass" | "warn" | "info" | "idle" }> = [
    {
      id: "stage1",
      label: "Stage 1",
      state: gate?.canonical_readout.exists ? "Frozen" : row?.stage1_session_id ? "In progress" : "Not started",
      tone: gate?.canonical_readout.exists ? "pass" : row?.stage1_session_id ? "info" : "idle"
    },
    {
      id: "stage2",
      label: "Stage 2",
      state: gate?.stage2_capture.exists ? "Complete" : gate?.canonical_readout.exists ? "Ready" : "Locked",
      tone: gate?.stage2_capture.exists ? "pass" : gate?.canonical_readout.exists ? "info" : "idle"
    },
    {
      id: "stage3",
      label: "Stage 3",
      state: gate?.stage3_pyramid.exists ? "Complete" : gate?.stage2_capture.exists ? "Ready" : "Locked",
      tone: gate?.stage3_pyramid.exists ? "pass" : gate?.stage2_capture.exists ? "info" : "idle"
    },
    {
      id: "stage4",
      label: "Stage 4",
      state: gate?.stage4_realized_expectancy.exists ? "Complete" : gate?.stage3_pyramid.exists ? "Ready" : "Locked",
      tone: gate?.stage4_realized_expectancy.exists ? "pass" : gate?.stage3_pyramid.exists ? "info" : "idle"
    }
  ];
  return (
    <div className="development-stage-tabs" role="tablist" aria-label="Development stages">
      {stages.map((stage) => (
        <button className={activeStage === stage.id ? "development-stage-tab is-active" : "development-stage-tab"} key={stage.id} onClick={() => onStageChange(stage.id)} type="button">
          <strong>{stage.label}</strong>
          <StatusBadge tone={stage.tone}>{stage.state}</StatusBadge>
        </button>
      ))}
    </div>
  );
}

function IterationDetailPanel({ detail }: { detail: Stage1IterationDetail }) {
  return (
    <div className="iteration-detail-layout">
      <div className="workbench-grid">
        <TerminalPanel eyebrow={detail.sample_role === "walk_forward_test" ? "walk-forward" : "training"} title="Score Summary">
          <div className="field-grid">
            <FieldRow label="Signals" value={formatNumber(detail.signal_count)} />
            <FieldRow label="Scoreable" value={formatNumber(detail.metrics.scoreable)} />
            <FieldRow label="Agreement" value={stage1Agreement(detail.metrics.directional_agreement)} />
            <FieldRow label="Threshold" value={`${detail.metrics.promotion_threshold_pct}%`} />
          </div>
        </TerminalPanel>
        <TerminalPanel eyebrow="artifacts" title="Bundle State">
          <div className="field-grid">
            <FieldRow label="Bundle" value={detail.bundle_role ?? "unknown"} />
            <FieldRow label="Matches" value={formatNumber(detail.metrics.matches)} />
            <FieldRow label="Mismatches" value={formatNumber(detail.metrics.mismatches)} />
            <FieldRow label="Neutral" value={formatNumber(detail.metrics.neutral)} />
          </div>
        </TerminalPanel>
      </div>

      <TerminalPanel className="scroll-panel" title="Monthly Clusters">
        <DataTable
          columns={[
            { key: "month", header: "Month", render: (item) => item.month },
            { key: "signals", header: "Signals", align: "right", render: (item) => formatNumber(item.metrics.total) },
            { key: "scoreable", header: "Scoreable", align: "right", render: (item) => formatNumber(item.metrics.scoreable) },
            { key: "matches", header: "Matches", align: "right", render: (item) => formatNumber(item.metrics.matches) },
            { key: "mismatches", header: "Mismatches", align: "right", render: (item) => formatNumber(item.metrics.mismatches) },
            { key: "neutral", header: "Neutral", align: "right", render: (item) => formatNumber(item.metrics.neutral) },
            { key: "agreement", header: "Agreement", align: "right", render: (item) => stage1Agreement(item.metrics.directional_agreement) },
          ]}
          getRowKey={(item) => item.month}
          rows={detail.monthly}
        />
      </TerminalPanel>

      <TerminalPanel className="scroll-panel" title="Signal Breakdown">
        <DataTable
          columns={[
            { key: "timestamp", header: "Timestamp", render: (item) => formatUtcTimestamp(item.timestamp) },
            { key: "signal_id", header: "Signal", render: (item) => item.signal_id },
            { key: "truth", header: "Truth", render: (item) => item.ground_truth_direction ?? "-" },
            { key: "decision", header: "Decision", render: (item) => item.decision_direction ?? "-" },
            { key: "agreement", header: "Outcome", render: (item) => item.agreement },
            { key: "confidence", header: "Confidence", align: "right", render: (item) => typeof item.confidence === "number" ? item.confidence.toFixed(2) : "-" },
            { key: "reason", header: "Reason", render: (item) => item.reason_code ?? "-" },
          ]}
          getRowKey={(item) => `${item.signal_id}-${item.timestamp ?? "na"}`}
          rows={detail.records}
        />
      </TerminalPanel>
    </div>
  );
}

function Stage1Panel({
  createBundlePending,
  gate,
  groupedIterations,
  iterations,
  loadingIterations,
  mode,
  onAudit,
  onCreateBundle,
  onDelete,
  onOpenIteration,
  onOpenPrompt,
  onRunCanonical,
  onResetSession,
  onScore,
  onStartStage1,
  row,
  runningCanonical,
  session,
  startingSession
}: {
  createBundlePending: boolean;
  gate: Stage1GateSummary | null;
  groupedIterations: Record<Stage1SampleRole, Stage1IterationSummary[]>;
  iterations: Stage1IterationSummary[];
  loadingIterations: boolean;
  mode: Stage1EvidenceMode;
  onAudit: (iteration: Stage1IterationSummary) => void;
  onCreateBundle: (role: Stage1SampleMethod) => void;
  onDelete: (iteration: Stage1IterationSummary) => void;
  onOpenIteration: (iteration: Stage1IterationSummary) => void;
  onOpenPrompt: (iteration: Stage1IterationSummary) => void;
  onRunCanonical: () => void;
  onResetSession: () => void;
  onScore: (iteration: Stage1IterationSummary) => void;
  onStartStage1: () => void;
  row: DevelopmentQueueRow | undefined;
  runningCanonical: boolean;
  session: Stage1ResearchSession | null;
  startingSession: boolean;
}) {
  const frozen = Boolean(gate?.canonical_readout.exists);
  const canForceFreeze = scoreExists(gate, "training") && scoreExists(gate, "walk_forward_test") && !gate?.ready_to_freeze;
  return (
    <div className="development-stage-body">
      <div className="workbench-grid">
        <TerminalPanel eyebrow="stage 1" title="Evidence Mode">
          <div className="stage1-mode-card">
            <div>
              <StatusBadge tone={mode.tone}>{mode.title}</StatusBadge>
              <strong>{mode.nextAction}</strong>
            </div>
            <FieldRow label="Allowed evidence" value={mode.allowedEvidence} />
            <FieldRow label="Agent use" value={mode.agentUse} />
          </div>
        </TerminalPanel>
        <TerminalPanel eyebrow="gate" title="Current Readout">
          <div className="field-grid">
            <FieldRow label="Training" value={`${gate?.roles.training?.status ?? "missing"} · ${gateScore(gate, "training")}`} />
            <FieldRow label="Walk-forward" value={`${gate?.roles.walk_forward_test?.status ?? "missing"} · ${gateScore(gate, "walk_forward_test")}`} />
            <FieldRow label="Freeze" value={frozen ? "complete" : gate?.ready_to_freeze ? "ready" : "blocked"} />
            <FieldRow label="MATCH set" value={frozen ? formatNumber(gate?.canonical_readout.match_count) : "not frozen"} />
          </div>
        </TerminalPanel>
      </div>

      {!session ? (
        <TerminalPanel title="Start Candidate Workspace">
          <div className="action-card">
            <span>{row ? `${row.asset} passed Training Pool. Create the pair-specific strategy workspace and inherit the pool windows.` : "Select an accepted candidate first."}</span>
            <button className="button button--primary" disabled={!row || startingSession} onClick={onStartStage1} type="button">
              <Play aria-hidden="true" />
              {startingSession ? "Starting" : "Start Stage 1"}
            </button>
          </div>
        </TerminalPanel>
      ) : (
        <>
          <TerminalPanel title="Session Controls">
            <div className="action-card action-card--inline">
              <span>Reset this candidate to the clean slate before Stage 1 started. This deletes the current session workspace and iteration history for this pool only.</span>
              <button
                className="button button--secondary"
                disabled={frozen}
                onClick={() => {
                  if (window.confirm("Reset this Stage 1 session back to clean slate?")) {
                    onResetSession();
                  }
                }}
                type="button"
              >
                Reset Session
              </button>
            </div>
          </TerminalPanel>
          <div className="stage1-lanes">
            {stage1Roles.map((role, index) => {
              const latest = groupedIterations[role][groupedIterations[role].length - 1];
              const score = latest ? stage1ScoreForRole(latest, role) : null;
              const status = gate?.roles[role]?.status ?? "missing";
              const walkForwardLocked = role === "walk_forward_test" && !scoreExists(gate, "training");
              return (
                <TerminalPanel eyebrow={`step ${index + 1}`} title={stage1RoleLabel(role)} key={role}>
                  <div className="field-stack">
                    <FieldRow label="Gate" value={status} />
                    <FieldRow label="Latest bundle" value={latest?.iteration_id ?? "none"} />
                    <FieldRow label="Signals" value={formatNumber(latest?.signal_count)} />
                    <FieldRow label="Score" value={score ? stage1Agreement(score.metrics.directional_agreement) : "not scored"} />
                  </div>
                  <button className="button button--secondary full-width-action" disabled={frozen || createBundlePending || walkForwardLocked} onClick={() => onCreateBundle(role)} type="button">
                    <Play aria-hidden="true" />
                    Create {role === "training" ? "Builder" : "Evaluator"} Bundle
                  </button>
                </TerminalPanel>
              );
            })}
            <TerminalPanel eyebrow="step 3" title="Freeze">
              <div className="field-stack">
                <FieldRow label="Status" value={frozen ? "complete" : gate?.ready_to_freeze ? "ready" : "blocked"} />
                <FieldRow label="Artifact" value="canonical Stage 1 decision set" />
                <FieldRow label="Downstream use" value="Stage 2-4" />
              </div>
              <button className="button button--primary full-width-action" disabled={frozen || runningCanonical || (!gate?.ready_to_freeze && !canForceFreeze)} onClick={onRunCanonical} type="button">
                <Play aria-hidden="true" />
                {frozen ? "Frozen" : runningCanonical ? "Freezing" : "Freeze Stage 1"}
              </button>
            </TerminalPanel>
          </div>

          <TerminalPanel className="iteration-ledger-panel" title="Iteration Ledger">
            {loadingIterations ? <div className="state-line">Loading iterations...</div> : null}
            <DataTable
              columns={[
                { key: "id", header: "Iteration", render: (iteration) => <strong>{iteration.iteration_id}</strong> },
                { key: "role", header: "Use", render: (iteration) => stage1RoleLabel(stage1RoleForIteration(iteration)) },
                { key: "bundle", header: "Bundle", render: (iteration) => stage1BundleLabel(iteration) },
                { key: "signals", header: "Signals", align: "right", render: (iteration) => formatNumber(iteration.signal_count) },
                { key: "score", header: "Score", align: "right", render: (iteration) => {
                  const score = stage1ScoreForRole(iteration, stage1RoleForIteration(iteration));
                  return score ? <span className={score.metrics.passes_threshold ? "tone-pass" : "tone-warn"}>{stage1Agreement(score.metrics.directional_agreement)}</span> : "not scored";
                } },
                { key: "audit", header: "Audit", render: (iteration) => iteration.has_failure_audit ? "ready" : "none" },
                { key: "actions", header: "Actions", align: "right", render: (iteration) => (
                  <div className="table-action-row">
                    <button className="button button--secondary" onClick={(event) => { event.stopPropagation(); onOpenPrompt(iteration); }} type="button">Prompt</button>
                    <button className="button button--secondary" disabled={frozen} onClick={(event) => { event.stopPropagation(); onScore(iteration); }} type="button">Score</button>
                    <button className="button button--secondary" disabled={frozen || !stage1ScoreForRole(iteration, stage1RoleForIteration(iteration))} onClick={(event) => { event.stopPropagation(); onAudit(iteration); }} type="button">Audit</button>
                    <button
                      className="icon-button"
                      disabled={frozen}
                      onClick={(event) => {
                        event.stopPropagation();
                        if (window.confirm(`Delete ${iteration.iteration_id}?`)) {
                          onDelete(iteration);
                        }
                      }}
                      type="button"
                      aria-label={`Delete ${iteration.iteration_id}`}
                    >
                      <Trash2 aria-hidden="true" />
                    </button>
                  </div>
                ) }
              ]}
              getRowKey={(iteration) => iteration.iteration_id}
              onRowClick={onOpenIteration}
              rows={iterations.slice().reverse()}
            />
          </TerminalPanel>
        </>
      )}
    </div>
  );
}

function StageRunProgress({ detail, steps, title }: { detail: string; steps: string[]; title: string }) {
  return (
    <div className="progress-card stage-run-progress">
      <div className="progress-card__header">
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <div className="progress-rail" aria-label={title}>
        <span />
      </div>
      <div className="progress-steps">
        {steps.map((step) => <span key={step}>{step}</span>)}
      </div>
    </div>
  );
}

type Stage2ExitPolicyDraft = {
  lock_profit_pct: number;
  protect_trigger_pct: number;
  trail_sl_pct: number;
};

function stage2TpOptions(stage2: Stage1GateSummary["stage2_capture"] | undefined): number[] {
  const values = stage2?.tp_levels?.length
    ? stage2.tp_levels
    : Object.keys(stage2?.results ?? {}).map((value) => Number(value));
  return Array.from(new Set(values.filter((value) => Number.isFinite(value)).map((value) => Number(value.toFixed(1))))).sort((a, b) => a - b);
}

function Stage2Panel({
  gate,
  onPromotePolicy,
  onRun,
  promotingPolicy,
  running
}: {
  gate: Stage1GateSummary | null;
  onPromotePolicy: (policy: Stage2ExitPolicyDraft) => void;
  onRun: () => void;
  promotingPolicy: boolean;
  running: boolean;
}) {
  const ready = Boolean(gate?.canonical_readout.exists);
  const stage2 = gate?.stage2_capture;
  const complete = Boolean(stage2?.exists);
  const policy = gate?.stage2_exit_policy;
  const tpOptions = useMemo(() => stage2TpOptions(stage2), [stage2?.results, stage2?.tp_levels]);
  const [policyDraft, setPolicyDraft] = useState<Stage2ExitPolicyDraft>({ lock_profit_pct: 0, protect_trigger_pct: 0, trail_sl_pct: 0 });

  useEffect(() => {
    const fallback = tpOptions[0] ?? 0;
    setPolicyDraft({
      lock_profit_pct: policy?.policy.lock_profit_pct ?? fallback,
      protect_trigger_pct: policy?.policy.protect_trigger_pct ?? fallback,
      trail_sl_pct: policy?.policy.trail_sl_pct ?? fallback
    });
  }, [policy?.policy.lock_profit_pct, policy?.policy.protect_trigger_pct, policy?.policy.trail_sl_pct, tpOptions]);

  const policyReady = complete && tpOptions.length > 0;
  return (
    <div className="development-stage-body">
      <TerminalPanel
        actions={
          <button className={running ? "button button--primary button--loading" : "button button--primary"} disabled={!ready || running} onClick={onRun} type="button">
            {running ? <RefreshCw aria-hidden="true" className="spin-icon" /> : <Play aria-hidden="true" />}
            {running ? "Capturing" : complete ? "Rerun Profile" : "Run Capture"}
          </button>
        }
        eyebrow="stage 2"
        title="Travel Capture"
      >
        {running ? (
          <StageRunProgress
            detail="Reading MATCH canonical decisions, walking forward 5m candles, and writing the TP band for setup search"
            steps={["Load MATCH trades", "Scan candles", "Profile travel", "Write TP band"]}
            title="Running Stage 2 capture"
          />
        ) : null}
        <div className="field-grid">
          <FieldRow label="Input" value="Canonical Stage 1 MATCH decisions" />
          <FieldRow label="State" value={running ? "running" : !ready ? "locked" : complete ? "complete" : "ready"} />
          <FieldRow label="Profiled matches" value={formatNumber(stage2?.metrics.stage2_profiled_match_count ?? stage2?.metrics.total_match_signals)} />
          <FieldRow label="Stage 3 trade pool" value={`${formatNumber(stage2?.match_count ?? stage2?.metrics.match_count)} MATCH / ${formatNumber(stage2?.mismatch_count ?? stage2?.metrics.mismatch_count)} MISMATCH`} />
          <FieldRow label="TP band" value={`${formatPct(stage2?.recommended_tp_min_pct)} - ${formatPct(stage2?.recommended_tp_max_pct)}`} />
          <FieldRow label="Artifact" value="MATCH travel curve + all-trade setup input" />
        </div>
        {policyReady ? (
          <div className="stage2-policy-card">
            <div className="stage2-policy-card__copy">
              <strong>Exit Policy Handoff</strong>
              <span>{policy?.exists ? "Promoted policy exists. Update it before rerunning Stage 3 if the exit setup changes." : "Select the numerical profit-protection policy before Stage 3."}</span>
            </div>
            <div className="stage2-policy-grid">
              <label>
                Lock Profit
                <select
                  value={policyDraft.lock_profit_pct}
                  onChange={(event) => setPolicyDraft({ ...policyDraft, lock_profit_pct: Number(event.target.value) })}
                >
                  {tpOptions.map((value) => <option key={value} value={value}>{formatPct(value)}</option>)}
                </select>
              </label>
              <label>
                Protect Trigger
                <select
                  value={policyDraft.protect_trigger_pct}
                  onChange={(event) => setPolicyDraft({ ...policyDraft, protect_trigger_pct: Number(event.target.value) })}
                >
                  {tpOptions.map((value) => <option key={value} value={value}>{formatPct(value)}</option>)}
                </select>
              </label>
              <label>
                Trail SL To
                <select
                  value={policyDraft.trail_sl_pct}
                  onChange={(event) => setPolicyDraft({ ...policyDraft, trail_sl_pct: Number(event.target.value) })}
                >
                  {tpOptions.map((value) => <option key={value} value={value}>{formatPct(value)}</option>)}
                </select>
              </label>
              <button className="button button--secondary" disabled={promotingPolicy} onClick={() => onPromotePolicy(policyDraft)} type="button">
                <UploadCloud aria-hidden="true" />
                {promotingPolicy ? "Promoting" : policy?.exists ? "Update Policy" : "Promote Policy"}
              </button>
            </div>
          </div>
        ) : null}
      </TerminalPanel>
      {complete && stage2 ? (
        <TerminalPanel className="scroll-panel" title="Capture Curve">
          <DataTable
            columns={[
              { key: "tp", header: "TP", render: (entry) => `${entry.level}%` },
              { key: "training", header: "Training", render: (entry) => formatCaptureRate(entry.rows.training) },
              { key: "walk", header: "Walk-forward", render: (entry) => formatCaptureRate(entry.rows.walk_forward_test) },
              { key: "full", header: "Full", render: (entry) => formatCaptureRate(entry.rows.full_cycle) }
            ]}
            getRowKey={(entry) => entry.level}
            rows={Object.entries(stage2.results).map(([level, rows]) => ({ level, rows }))}
          />
        </TerminalPanel>
      ) : null}
    </div>
  );
}

function Stage3Panel({
  gate,
  exactProtectionRunning,
  fixedSlRunning,
  localVariantsRunning,
  onRunExactProtection,
  onRunFixedSl,
  onRunLocalVariants,
  onRunPyramid,
  pyramidRunning
}: {
  gate: Stage1GateSummary | null;
  exactProtectionRunning: boolean;
  fixedSlRunning: boolean;
  localVariantsRunning: boolean;
  onRunExactProtection: () => void;
  onRunFixedSl: () => void;
  onRunLocalVariants: () => void;
  onRunPyramid: () => void;
  pyramidRunning: boolean;
}) {
  const stage2Ready = Boolean(gate?.stage2_capture.exists);
  const policyReady = Boolean(gate?.stage2_exit_policy.exists);
  const grid = gate?.stage3_grid;
  const pyramid = gate?.stage3_pyramid;
  const fixed = grid?.fixed_sl_baseline_result;
  const exact = grid?.exact_protection_result ?? grid?.exact_policy_result;
  const ranges = grid?.stage3c_value_ranges;
  const fixedComplete = Boolean(grid?.fixed_sl_complete || fixed?.config_id);
  const exactComplete = Boolean(grid?.exact_protection_complete || exact?.config_id);
  const localComplete = Boolean(grid?.local_variants_complete || grid?.exists);
  const stage0InitialSl = grid?.stage0_risk_policy?.initial_sl_pct;
  const stage0HardExit = grid?.stage0_risk_policy?.hard_exit_hours;
  const pyramidBest = pyramid?.best ?? {};
  const pyramidBaseline = pyramid?.baseline ?? {};
  const pyramidRows = [...(pyramid?.results ?? [])].sort((left, right) => {
    const leftPnl = Number(left.pnl_pct ?? Number.NEGATIVE_INFINITY);
    const rightPnl = Number(right.pnl_pct ?? Number.NEGATIVE_INFINITY);
    return rightPnl - leftPnl;
  }).slice(0, 8);
  const bestSourceSetup = pyramidBest.source_setup ?? {};
  const bestPyramidMode = bestSourceSetup.protection_enabled ? "Protected SL" : "Fixed SL";
  return (
    <div className="development-stage-body">
      <div className="workbench-grid">
        <TerminalPanel
          actions={
            <button className={fixedSlRunning ? "button button--primary button--loading" : "button button--primary"} disabled={!stage2Ready || !policyReady || fixedSlRunning} onClick={onRunFixedSl} type="button">
              {fixedSlRunning ? <RefreshCw aria-hidden="true" className="spin-icon" /> : <Play aria-hidden="true" />}
              {fixedSlRunning ? "Testing" : fixedComplete ? "Rerun Fixed SL" : "Run Fixed SL"}
            </button>
          }
          eyebrow="stage 3a"
          title="Fixed SL Baseline"
        >
          {!policyReady ? <div className="state-line state-line--warn">Promote a Stage 2 exit policy before running Stage 3.</div> : null}
          {fixedSlRunning ? (
            <StageRunProgress
              detail="Testing the Stage 2 TP with the original Stage 0 stop and no stop movement"
              steps={["Load executable decisions", "Apply fixed TP/SL", "Walk 5m candles", "Write baseline"]}
              title="Running fixed SL baseline"
            />
          ) : null}
          <div className="field-grid">
            <FieldRow label="Input" value="Stage 2 final TP + Stage 0 risk" />
            <FieldRow label="Policy" value={policyReady ? "promoted" : "missing"} />
            <FieldRow label="Original SL" value={formatPct(stage0InitialSl)} />
            <FieldRow label="Hard exit" value={stage0HardExit ? `${formatNumber(stage0HardExit)}h` : "n/a"} />
            <FieldRow label="Executable decisions" value={formatNumber(grid?.total_executable_decisions ?? grid?.total_signals)} />
            <FieldRow label="TP / SL" value={`${formatPct(fixed?.final_tp_pct ?? fixed?.tp)} / ${formatPct(fixed?.initial_sl_pct ?? fixed?.sl)}`} />
            <FieldRow label="Hits" value={`${formatNumber(fixed?.tp_count ?? 0)} TP / ${formatNumber(fixed?.initial_sl_count ?? 0)} SL / ${formatNumber(fixed?.time_exit_count ?? 0)} time`} />
            <FieldRow label="Net PnL" value={formatPct(fixed?.net_pnl_pct ?? fixed?.pnl_pct)} />
          </div>
        </TerminalPanel>
        <TerminalPanel
          actions={
            <button className={exactProtectionRunning ? "button button--primary button--loading" : "button button--primary"} disabled={!fixedComplete || exactProtectionRunning} onClick={onRunExactProtection} type="button">
              {exactProtectionRunning ? <RefreshCw aria-hidden="true" className="spin-icon" /> : <Play aria-hidden="true" />}
              {exactProtectionRunning ? "Testing" : exactComplete ? "Rerun Protection" : "Run Protection"}
            </button>
          }
          eyebrow="stage 3b"
          title="Exact Protection"
        >
          {exactProtectionRunning ? (
            <StageRunProgress
              detail="Testing the promoted Stage 2 protect trigger and protected stop exactly"
              steps={["Load baseline", "Activate protection after trigger", "Track protected SL", "Write exact result"]}
              title="Running exact protection test"
            />
          ) : null}
          <div className="field-grid">
            <FieldRow label="Input" value="3A baseline + Stage 2 protection policy" />
            <FieldRow label="Trigger / protected SL" value={`${formatPct(exact?.protect_trigger_pct)} / ${formatPct(exact?.trail_sl_pct)}`} />
            <FieldRow label="TP / initial SL" value={`${formatPct(exact?.final_tp_pct ?? exact?.tp)} / ${formatPct(exact?.initial_sl_pct ?? exact?.sl)}`} />
            <FieldRow label="Hits" value={`${formatNumber(exact?.tp_count ?? 0)} TP / ${formatNumber(exact?.initial_sl_count ?? 0)} init SL / ${formatNumber(exact?.protected_sl_count ?? 0)} protected`} />
            <FieldRow label="Win rate" value={formatPct(exact?.wr)} />
            <FieldRow label="Net PnL" value={formatPct(exact?.net_pnl_pct ?? exact?.pnl_pct)} />
          </div>
        </TerminalPanel>
      </div>
      <div className="workbench-grid">
        <TerminalPanel
          className="scroll-panel"
          actions={
            <button className={localVariantsRunning ? "button button--primary button--loading" : "button button--primary"} disabled={!exactComplete || localVariantsRunning} onClick={onRunLocalVariants} type="button">
              {localVariantsRunning ? <RefreshCw aria-hidden="true" className="spin-icon" /> : <Play aria-hidden="true" />}
              {localVariantsRunning ? "Testing" : localComplete ? "Rerun Variants" : "Run Variants"}
            </button>
          }
          eyebrow="stage 3c"
          title="Local Variants"
        >
          {localVariantsRunning ? (
            <StageRunProgress
              detail="Testing all valid adjacent TP/protect/trail/SL permutations"
              steps={["Build adjacent grid", "Walk candles", "Rank every setup", "Write Stage 4 candidates"]}
              title="Running local variant test"
            />
          ) : null}
          <div className="field-grid">
            <FieldRow label="Input" value="3A + 3B results" />
            <FieldRow label="Combinations" value={formatNumber(grid?.stage3c_total_combinations_tested)} />
            <FieldRow label="TP values" value={formatRangeList(ranges?.final_tp_pct)} />
            <FieldRow label="Protect values" value={formatRangeList(ranges?.protect_trigger_pct)} />
            <FieldRow label="Trail SL values" value={formatRangeList(ranges?.trail_sl_pct)} />
          </div>
          {localComplete ? (
            <DataTable
              columns={[
                { key: "mode", header: "Mode", render: (item) => item.protection_enabled ? "Protected" : "Fixed SL" },
                { key: "setup", header: "Policy", render: (item) => `${formatPct(item.final_tp_pct ?? item.tp)} TP / ${formatPct(item.initial_sl_pct ?? item.sl)} SL` },
                { key: "protect", header: "Protect / Trail", render: (item) => `${formatPct(item.protect_trigger_pct)} / ${formatPct(item.trail_sl_pct)}` },
                { key: "wr", header: "WR", align: "right", render: (item) => formatPct(item.wr) },
                { key: "hits", header: "TP / Init SL / Prot SL / Time", render: (item) => `${formatNumber(item.tp_count)} / ${formatNumber(item.initial_sl_count ?? 0)} / ${formatNumber(item.protected_sl_count ?? 0)} / ${formatNumber(item.time_exit_count ?? item.neither)}` },
                { key: "pf", header: "PF", align: "right", render: (item) => item.profit_factor === 999 ? "inf" : item.profit_factor.toFixed(2) },
                { key: "pnl", header: "PnL", align: "right", render: (item) => formatPct(item.pnl_pct) }
              ]}
              getRowKey={(item) => `${item.stage3_step}-${item.final_tp_pct ?? item.tp}-${item.initial_sl_pct ?? item.sl}-${item.protect_trigger_pct}-${item.trail_sl_pct}`}
              rows={grid?.top_5 ?? []}
            />
          ) : null}
        </TerminalPanel>
        <TerminalPanel
          className="scroll-panel"
          actions={
            <button className={pyramidRunning ? "button button--primary button--loading" : "button button--primary"} disabled={!localComplete || pyramidRunning} onClick={onRunPyramid} type="button">
              {pyramidRunning ? <RefreshCw aria-hidden="true" className="spin-icon" /> : <Play aria-hidden="true" />}
              {pyramidRunning ? "Searching" : pyramid?.exists ? "Rerun Pyramid" : "Run Pyramid"}
            </button>
          }
          eyebrow="stage 3d"
          title="Pyramiding"
        >
          {pyramidRunning ? (
            <StageRunProgress
              detail="Testing pyramid spacing and leg behavior from the Stage 3C shortlist"
              steps={["Load Stage 3C top 5", "Sweep max legs", "Compare baseline", "Write setup"]}
              title="Running pyramiding test"
            />
          ) : null}
          <div className="field-grid">
            <FieldRow label="Input" value="Stage 3C top 5" />
            <FieldRow label="Mode" value={pyramid?.exists ? bestPyramidMode : "not tested"} />
            <FieldRow label="Baseline PnL" value={formatPct(pyramidBaseline.pnl_pct)} />
            <FieldRow label="Best legs / step" value={`${formatNumber(pyramidBest.max_legs ?? pyramid?.max_legs)} legs / ${formatPct(pyramidBest.step_pct)}`} />
            <FieldRow label="TP / SL" value={`${formatPct(pyramidBest.tp_pct ?? pyramid?.tp_pct)} / ${formatPct(pyramidBest.sl_pct ?? pyramid?.sl_pct)}`} />
            <FieldRow label="Avg legs" value={formatDecimal(pyramidBest.avg_legs_per_signal)} />
            <FieldRow label="Delta vs baseline" value={formatPct(pyramidBest.delta_vs_baseline_pct)} />
            <FieldRow label="Wins / losses" value={`${formatNumber(pyramidBest.wins)} / ${formatNumber(pyramidBest.losses)}`} />
            <FieldRow label="Net PnL" value={formatPct(pyramidBest.pnl_pct)} />
          </div>
          {pyramid?.exists ? (
            <DataTable
              columns={[
                { key: "source", header: "Source", render: (item) => item.source_candidate_id ? shortId(item.source_candidate_id) : "baseline" },
                { key: "setup", header: "Setup", render: (item) => `${formatPct(item.tp_pct ?? pyramid.tp_pct)} TP / ${formatPct(item.sl_pct ?? pyramid.sl_pct)} SL` },
                { key: "legs", header: "Legs / Step", render: (item) => `${formatNumber(item.max_legs)} / ${item.step_pct == null ? "base" : formatPct(item.step_pct)}` },
                { key: "avg", header: "Avg Legs", align: "right", render: (item) => formatDecimal(item.avg_legs_per_signal) },
                { key: "wl", header: "W / L", align: "right", render: (item) => `${formatNumber(item.wins)} / ${formatNumber(item.losses)}` },
                { key: "delta", header: "Delta", align: "right", render: (item) => formatPct(item.delta_vs_baseline_pct) },
                { key: "pnl", header: "PnL", align: "right", render: (item) => formatPct(item.pnl_pct) }
              ]}
              getRowKey={(item) => `${item.source_candidate_id ?? "baseline"}-${item.max_legs}-${item.step_pct ?? "base"}-${item.pnl_pct}`}
              rows={pyramidRows}
            />
          ) : null}
        </TerminalPanel>
      </div>
    </div>
  );
}

function Stage4Panel({
  gate,
  onPromote,
  onRun,
  inputs,
  onInputsChange,
  promoting,
  running
}: {
  gate: Stage1GateSummary | null;
  onPromote: () => void;
  onRun: () => void;
  inputs: { initial_capital_usdt: number; margin_allocation_pct: number; leverage: number };
  onInputsChange: (inputs: { initial_capital_usdt: number; margin_allocation_pct: number; leverage: number }) => void;
  promoting: boolean;
  running: boolean;
}) {
  const ready = Boolean(gate?.stage3_pyramid.exists);
  const stage4 = gate?.stage4_realized_expectancy;
  const complete = Boolean(stage4?.exists);
  const best = stage4?.best_candidate ?? {};
  const account = best.account ?? {};
  const latestInputs = stage4?.latest_simulation_inputs ?? null;
  const inputsDirty = Boolean(
    complete && latestInputs && (
      Number(latestInputs.initial_capital_usdt) !== Number(inputs.initial_capital_usdt)
      || Number(latestInputs.margin_allocation_pct) !== Number(inputs.margin_allocation_pct)
      || Number(latestInputs.leverage) !== Number(inputs.leverage)
    )
  );
  const runLabel = running ? "Backtesting" : complete ? inputsDirty ? "Run Updated Test" : "Run New Test" : "Run Expectancy";
  const bestSetup = best.setup ?? {};
  const exitMode = bestSetup.protection_enabled ? "Protected SL" : "Fixed SL";
  const pyramid = bestSetup.pyramid;
  return (
    <div className="development-stage-body">
      <TerminalPanel
        actions={
          <>
            <button className={running ? "button button--primary button--loading" : "button button--primary"} disabled={!ready || running} onClick={onRun} type="button">
              {running ? <RefreshCw aria-hidden="true" className="spin-icon" /> : <Play aria-hidden="true" />}
              {runLabel}
            </button>
            <button className="button button--secondary" disabled={!complete || promoting || inputsDirty} onClick={onPromote} type="button"><UploadCloud aria-hidden="true" />{promoting ? "Promoting" : "Promote"}</button>
          </>
        }
        eyebrow="stage 4"
        title="Realized Expectancy"
      >
        {inputsDirty ? <div className="state-line state-line--warn">Setup changed - rerun before promotion.</div> : null}
        {running ? (
          <StageRunProgress
            detail="Walking canonical decisions sequentially, simulating positions, fees, pyramids, and hard exits"
            steps={["Load decisions", "Replay candles", "Simulate account", "Write ledger"]}
            title="Running sequential Stage 4 backtest"
          />
        ) : null}
        <div className="stage4-setup-strip">
          <div className="stage4-setup-strip__title">
            <strong>Simulation Setup</strong>
            <span>Rerun whenever capital, margin, or leverage changes.</span>
          </div>
          <label className="stage4-number-control">
            <span>Capital</span>
            <input
              min="1"
              step="100"
              type="number"
              value={inputs.initial_capital_usdt}
              onChange={(event) => onInputsChange({ ...inputs, initial_capital_usdt: Number(event.target.value) })}
            />
            <em>USDT</em>
          </label>
          <label className="stage4-slider-control">
            <span>Margin</span>
            <input
              min="1"
              max="100"
              step="1"
              type="range"
              value={inputs.margin_allocation_pct}
              onChange={(event) => onInputsChange({ ...inputs, margin_allocation_pct: Number(event.target.value) })}
            />
            <strong>{formatPct(inputs.margin_allocation_pct)}</strong>
          </label>
          <label className="stage4-slider-control">
            <span>Leverage</span>
            <input
              min="1"
              max="20"
              step="1"
              type="range"
              value={inputs.leverage}
              onChange={(event) => onInputsChange({ ...inputs, leverage: Number(event.target.value) })}
            />
            <strong>{formatNumber(inputs.leverage)}x</strong>
          </label>
        </div>
        <div className="stage4-result-strip">
          <div>
            <span>Best Candidate</span>
            <strong>{stage4?.best_candidate_id ?? best.candidate_id ?? "n/a"}</strong>
          </div>
          <div>
            <span>Net Expectancy</span>
            <strong>{formatPct(best.net_expectancy_pct)}</strong>
          </div>
          <div>
            <span>Trades</span>
            <strong>{formatNumber(best.executed_trades)}</strong>
          </div>
          <div>
            <span>Ending Equity</span>
            <strong>{formatUsd(account.ending_equity_usdt)}</strong>
          </div>
          <div>
            <span>Net PnL</span>
            <strong>{formatUsd(account.net_pnl_usdt)}</strong>
          </div>
          <div>
            <span>Fees</span>
            <strong>{formatUsd(account.total_fees_usdt)}</strong>
          </div>
        </div>
        <div className="stage4-footnote-grid">
          <FieldRow label="Input" value="Stage 4 candidates + full canonical decisions" />
          <FieldRow label="Simulator" value="Sequential account backtest" />
          <FieldRow label="Exit mode" value={best.candidate_id ? exitMode : "n/a"} />
          <FieldRow label="TP / Initial SL" value={`${formatPct(bestSetup.final_tp_pct ?? bestSetup.tp_pct)} / ${formatPct(bestSetup.initial_sl_pct ?? bestSetup.sl_pct)}`} />
          <FieldRow label="Protect / Trail" value={bestSetup.protection_enabled ? `${formatPct(bestSetup.protect_trigger_pct)} / ${formatPct(bestSetup.trail_sl_pct)}` : "off"} />
          <FieldRow label="Hard exit" value={bestSetup.max_hold_hours ? `${formatNumber(bestSetup.max_hold_hours)}h` : "n/a"} />
          <FieldRow label="Pyramid" value={pyramid ? `${formatNumber(pyramid.max_legs)} legs @ ${formatPct(pyramid.step_pct)}` : "off"} />
          <FieldRow label="Fees" value="OKX USDT swap taker default, 5 bps per fill" />
          <FieldRow label="Position-open skips" value={formatNumber(best.skipped_position_open)} />
          <FieldRow label="Initial / Protected SL" value={`${formatNumber(best.initial_sl_hits)} / ${formatNumber(best.protected_sl_hits)}`} />
          <FieldRow label="Latest run" value={stage4?.latest_run_id ?? "n/a"} />
        </div>
      </TerminalPanel>
      {complete && stage4 ? (
        <TerminalPanel className="scroll-panel" title="Candidate Results">
          <DataTable
            columns={[
              { key: "id", header: "Candidate", render: (item) => item.candidate_id },
              { key: "net", header: "Net Exp", align: "right", render: (item) => formatPct(item.net_expectancy_pct) },
              { key: "trades", header: "Trades", align: "right", render: (item) => formatNumber(item.executed_trades) },
              { key: "win", header: "Win Rate", align: "right", render: (item) => formatPct(item.win_rate_pct) },
              { key: "pnl", header: "Account PnL", align: "right", render: (item) => formatPct(item.net_pnl_pct) },
              { key: "fees", header: "Fees", align: "right", render: (item) => formatUsd(item.account?.total_fees_usdt) }
            ]}
            getRowKey={(item) => item.candidate_id}
            rows={stage4.candidates}
          />
        </TerminalPanel>
      ) : null}
      {stage4?.stage4_runs?.length ? (
        <TerminalPanel className="scroll-panel" title="Stage 4 Run History">
          <DataTable
            columns={[
              { key: "time", header: "Run", render: (item) => item.created_at?.replace("T", " ").replace("Z", " UTC") ?? item.run_id },
              { key: "setup", header: "Setup", render: (item) => `${formatUsd(item.simulation_inputs.initial_capital_usdt)} · ${formatPct(item.simulation_inputs.margin_allocation_pct)} · ${formatNumber(item.simulation_inputs.leverage)}x` },
              { key: "candidate", header: "Best", render: (item) => item.best_candidate_id ?? "n/a" },
              { key: "equity", header: "Ending Equity", align: "right", render: (item) => formatUsd(item.account?.ending_equity_usdt) },
              { key: "pnl", header: "Net PnL", align: "right", render: (item) => formatUsd(item.account?.net_pnl_usdt) },
              { key: "fees", header: "Fees", align: "right", render: (item) => formatUsd(item.account?.total_fees_usdt) }
            ]}
            getRowKey={(item) => item.run_id}
            rows={stage4.stage4_runs.slice().reverse()}
          />
        </TerminalPanel>
      ) : null}
    </div>
  );
}
