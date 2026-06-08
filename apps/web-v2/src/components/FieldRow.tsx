type FieldRowProps = {
  label: string;
  value: string;
  tone?: "default" | "pass" | "risk" | "warn";
};

export function FieldRow({ label, value, tone = "default" }: FieldRowProps) {
  return (
    <div className="field-row">
      <span>{label}</span>
      <strong className={tone === "default" ? undefined : `tone-${tone}`}>{value}</strong>
    </div>
  );
}
