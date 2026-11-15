// The charts live in components/viz and are drawn with d3. This is the one
// inline gauge that sits in tables and lists, and it needs no script.

/** A confidence bar with the refusal threshold marked on it. It grows in with CSS. */
export function Meter({ value, threshold }: { value: number; threshold?: number }) {
  const pass = threshold !== undefined && value >= threshold;
  return (
    <div
      className={`meter${pass ? " pass" : ""}`}
      role="meter"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-label={`confidence ${value.toFixed(2)}`}
    >
      <div className="fill" style={{ width: `${Math.min(100, value * 100)}%` }} />
      {threshold !== undefined && (
        <div className="threshold" style={{ left: `${threshold * 100}%` }} title={`refusal threshold ${threshold}`} />
      )}
    </div>
  );
}
