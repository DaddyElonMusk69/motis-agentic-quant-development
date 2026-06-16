import type { Stage1IterationDetail, Stage1IterationDetailRecord } from "./api";

export type Stage1ConsistencySide = {
  side: "LONG" | "SHORT";
  truthCount: number;
  callCount: number;
  matches: number;
  mismatches: number;
  agreement: number | null;
};

export type Stage1ConsistencyMonth = {
  month: string;
  total: number;
  scoreable: number;
  matches: number;
  mismatches: number;
  neutral: number;
  called: number;
  directionalAgreement: number | null;
  calledCoverage: number | null;
  skipRate: number | null;
  naturalNullRate: number | null;
  neutralDeviation: number | null;
  longAgreement: number | null;
  shortAgreement: number | null;
  flags: string[];
};

export type Stage1ConsistencySummary = {
  total: number;
  called: number;
  neutral: number;
  calledCoverage: number | null;
  skipRate: number | null;
  naturalNullRate: number | null;
  neutralDeviation: number | null;
  directionalAgreement: number | null;
  sideImbalance: number | null;
  worstMonth: Stage1ConsistencyMonth | null;
  highestSkipMonth: Stage1ConsistencyMonth | null;
};

export type Stage1ConsistencyView = {
  summary: Stage1ConsistencySummary;
  sides: Stage1ConsistencySide[];
  months: Stage1ConsistencyMonth[];
};

const SIDES = ["LONG", "SHORT"] as const;

function isSide(value: string | null | undefined): value is "LONG" | "SHORT" {
  return value === "LONG" || value === "SHORT";
}

function divide(numerator: number, denominator: number): number | null {
  return denominator > 0 ? numerator / denominator : null;
}

function agreement(records: Stage1IterationDetailRecord[]): number | null {
  const matches = records.filter((record) => record.agreement === "MATCH").length;
  const mismatches = records.filter((record) => record.agreement === "MISMATCH").length;
  return divide(matches, matches + mismatches);
}

function sideAgreement(records: Stage1IterationDetailRecord[], side: "LONG" | "SHORT"): number | null {
  const sideCalls = records.filter((record) => record.decision_direction === side);
  const matches = sideCalls.filter((record) => record.agreement === "MATCH").length;
  const mismatches = sideCalls.filter((record) => record.agreement === "MISMATCH").length;
  return divide(matches, matches + mismatches);
}

function monthKey(record: Stage1IterationDetailRecord): string {
  const timestamp = record.timestamp;
  return typeof timestamp === "string" && timestamp.length >= 7 ? timestamp.slice(0, 7) : "unknown";
}

function buildMonth(month: string, records: Stage1IterationDetailRecord[], aggregateCoverage: number | null): Stage1ConsistencyMonth {
  const total = records.length;
  const matches = records.filter((record) => record.agreement === "MATCH").length;
  const mismatches = records.filter((record) => record.agreement === "MISMATCH").length;
  const neutral = records.filter((record) => record.agreement === "NEUTRAL").length;
  const called = records.filter((record) => isSide(record.decision_direction)).length;
  const nullGroundTruth = records.filter((record) => !isSide(record.ground_truth_direction)).length;
  const directionalAgreement = divide(matches, matches + mismatches);
  const calledCoverage = divide(called, total);
  const skipRate = divide(neutral, total);
  const naturalNullRate = divide(nullGroundTruth, total);
  const neutralDeviation = skipRate !== null && naturalNullRate !== null ? skipRate - naturalNullRate : null;
  const longAgreement = sideAgreement(records, "LONG");
  const shortAgreement = sideAgreement(records, "SHORT");
  const flags: string[] = [];

  if (total >= 10 && directionalAgreement !== null && directionalAgreement < 0.5) {
    flags.push("low agreement");
  }
  if (aggregateCoverage !== null && calledCoverage !== null && aggregateCoverage - calledCoverage >= 0.15) {
    flags.push("coverage drop");
  }
  if (neutralDeviation !== null && neutralDeviation >= 0.25) {
    flags.push("skip drift");
  }
  if (neutralDeviation !== null && neutralDeviation <= -0.25) {
    flags.push("over-calling");
  }
  if ((longAgreement !== null && longAgreement < 0.5) || (shortAgreement !== null && shortAgreement < 0.5)) {
    flags.push("side weak");
  }

  return {
    month,
    total,
    scoreable: matches + mismatches,
    matches,
    mismatches,
    neutral,
    called,
    directionalAgreement,
    calledCoverage,
    skipRate,
    naturalNullRate,
    neutralDeviation,
    longAgreement,
    shortAgreement,
    flags,
  };
}

export function buildStage1Consistency(detail: Stage1IterationDetail): Stage1ConsistencyView {
  const records = detail.records ?? [];
  const total = records.length || detail.signal_count || detail.metrics.total || 0;
  const called = records.filter((record) => isSide(record.decision_direction)).length;
  const neutral = records.filter((record) => record.agreement === "NEUTRAL" || !isSide(record.decision_direction)).length;
  const nullGroundTruth = records.filter((record) => !isSide(record.ground_truth_direction)).length;
  const calledCoverage = divide(called, total);
  const skipRate = divide(neutral, total);
  const naturalNullRate = divide(nullGroundTruth, total);
  const neutralDeviation = skipRate !== null && naturalNullRate !== null ? skipRate - naturalNullRate : null;
  const directionalAgreement = detail.metrics.directional_agreement ?? agreement(records);
  const sideImbalance = called > 0
    ? Math.abs(
      records.filter((record) => record.decision_direction === "LONG").length -
      records.filter((record) => record.decision_direction === "SHORT").length
    ) / called
    : null;

  const groups = new Map<string, Stage1IterationDetailRecord[]>();
  for (const record of records) {
    const key = monthKey(record);
    groups.set(key, [...(groups.get(key) ?? []), record]);
  }
  for (const monthly of detail.monthly ?? []) {
    if (!groups.has(monthly.month)) {
      groups.set(monthly.month, []);
    }
  }

  const months = Array.from(groups.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([month, monthRecords]) => buildMonth(month, monthRecords, calledCoverage));
  const worstMonth = months.reduce<Stage1ConsistencyMonth | null>((worst, month) => {
    if (month.directionalAgreement === null) {
      return worst;
    }
    if (!worst || worst.directionalAgreement === null || month.directionalAgreement < worst.directionalAgreement) {
      return month;
    }
    return worst;
  }, null);
  const highestSkipMonth = months.reduce<Stage1ConsistencyMonth | null>((highest, month) => {
    if (month.skipRate === null) {
      return highest;
    }
    if (!highest || highest.skipRate === null || month.skipRate > highest.skipRate) {
      return month;
    }
    return highest;
  }, null);

  const sides = SIDES.map((side) => {
    const sideCalls = records.filter((record) => record.decision_direction === side);
    const matches = sideCalls.filter((record) => record.agreement === "MATCH").length;
    const mismatches = sideCalls.filter((record) => record.agreement === "MISMATCH").length;
    return {
      side,
      truthCount: records.filter((record) => record.ground_truth_direction === side).length,
      callCount: sideCalls.length,
      matches,
      mismatches,
      agreement: divide(matches, matches + mismatches),
    };
  });

  return {
    summary: {
      total,
      called,
      neutral,
      calledCoverage,
      skipRate,
      naturalNullRate,
      neutralDeviation,
      directionalAgreement,
      sideImbalance,
      worstMonth,
      highestSkipMonth,
    },
    sides,
    months,
  };
}
