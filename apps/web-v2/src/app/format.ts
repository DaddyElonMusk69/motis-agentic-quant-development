export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "n/a";
  }
  return value.toLocaleString();
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  return value.replace("T", " ").replace("Z", " UTC");
}

export function formatCompactValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
  }
  return String(value);
}
