import type { CalibrationBin } from "@/lib/types";

/** A confidence bar with the refusal threshold marked on it. */
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

/**
 * Reliability diagram: when the system says 30%, is it right about 30% of the
 * time? Bars are what happened, the diagonal is perfect honesty.
 */
export function Calibration({ bins }: { bins: CalibrationBin[] }) {
  const size = 280;
  const pad = 36;
  const inner = size - pad - 12;
  const sx = (v: number) => pad + v * inner;
  const sy = (v: number) => size - pad - v * inner;
  const maxN = Math.max(1, ...bins.map((b) => b.n));
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      style={{ width: "100%", maxWidth: 360, height: "auto", display: "block" }}
      role="img"
      aria-label="Reliability diagram comparing stated confidence to how often claims turned out true"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line x1={sx(0)} x2={sx(1)} y1={sy(t)} y2={sy(t)} stroke="var(--rule)" />
          <text x={pad - 6} y={sy(t) + 4} fontSize="10" textAnchor="end" fill="var(--muted)" fontFamily="var(--font-mono)">
            {t}
          </text>
          <text x={sx(t)} y={size - pad + 16} fontSize="10" textAnchor="middle" fill="var(--muted)" fontFamily="var(--font-mono)">
            {t}
          </text>
        </g>
      ))}
      <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--muted)" strokeDasharray="4 4" />
      {bins.map((b) => {
        const w = (b.upper - b.lower) * inner - 6;
        const h = b.observed_frequency * inner;
        return (
          <g key={b.lower}>
            <title>
              {`${b.n} claims stated ${b.lower}–${b.upper}; mean stated ${b.mean_confidence.toFixed(2)}, true ${(b.observed_frequency * 100).toFixed(0)}% of the time`}
            </title>
            <rect
              x={sx(b.lower) + 3}
              y={sy(0) - h}
              width={w}
              height={h}
              fill="var(--accent)"
              opacity={b.n === 0 ? 0 : 0.25 + 0.75 * (b.n / maxN)}
            />
            {b.n > 0 && (
              <circle cx={sx(b.mean_confidence)} cy={sy(b.observed_frequency)} r="3.5" fill="var(--ink)" />
            )}
            <text
              x={sx(b.lower) + 3 + w / 2}
              y={sy(0) - h - 5}
              fontSize="10"
              textAnchor="middle"
              fill="var(--ink-2)"
              fontFamily="var(--font-mono)"
            >
              n={b.n}
            </text>
          </g>
        );
      })}
      <text x={sx(0.5)} y={size - 4} fontSize="10" textAnchor="middle" fill="var(--ink-2)">
        confidence the system stated
      </text>
      <text
        x={10}
        y={sy(0.5)}
        fontSize="10"
        textAnchor="middle"
        fill="var(--ink-2)"
        transform={`rotate(-90 10 ${sy(0.5)})`}
      >
        how often it was right
      </text>
    </svg>
  );
}

/** A horizontal bar row for comparing one metric across ablations or slices. */
export function BarRow({
  label,
  value,
  max,
  display,
  emphasis,
}: {
  label: React.ReactNode;
  value: number;
  max: number;
  display: string;
  emphasis?: boolean;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 190px) 1fr 56px", gap: 12, alignItems: "center", padding: "5px 0" }}>
      <div className="small" style={{ fontWeight: emphasis ? 600 : 400 }}>
        {label}
      </div>
      <div style={{ height: 10, background: "var(--paper-3)", borderRadius: 1 }}>
        <div
          style={{
            width: `${max > 0 ? Math.min(100, (value / max) * 100) : 0}%`,
            height: "100%",
            background: emphasis ? "var(--accent)" : "var(--ink)",
            borderRadius: 1,
          }}
        />
      </div>
      <div className="mono small" style={{ textAlign: "right" }}>
        {display}
      </div>
    </div>
  );
}
