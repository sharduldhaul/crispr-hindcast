"use client";

// The controls above a zoomable chart: a few named views, and a line that says
// what is showing or how to zoom. Brushing and double-click do the same work;
// these buttons are the path for touch and keyboard.

export interface ZoomPreset {
  key: string;
  label: string;
}

export function ZoomBar({
  presets,
  active,
  onPick,
  status,
}: {
  presets: ZoomPreset[];
  /** The preset showing, or null when the reader brushed a view of their own. */
  active: string | null;
  onPick: (key: string) => void;
  status: React.ReactNode;
}) {
  return (
    <div className="viz-zoom">
      <div className="segmented sm" role="group" aria-label="Zoom">
        {presets.map((p) => (
          <button key={p.key} type="button" aria-pressed={active === p.key} onClick={() => onPick(p.key)}>
            {p.label}
          </button>
        ))}
      </div>
      <span className="viz-hint" aria-live="polite">
        {status}
      </span>
    </div>
  );
}
