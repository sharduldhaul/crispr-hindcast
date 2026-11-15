"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

interface Props {
  slices: readonly string[];
  ablations: readonly string[];
  primary: string;
  status: { hasVenv: boolean; hasGraph: boolean; hasResults: boolean };
}

type Action = { action: string; cutoff?: string; ablation?: string };

const EXIT = /__HINDCAST_EXIT__ (-?\d+)\s*$/;

export function RunConsole({ slices, ablations, primary, status }: Props) {
  const router = useRouter();
  const [output, setOutput] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [cutoff, setCutoff] = useState(primary);
  const [ablation, setAblation] = useState(ablations[0]);
  const [lastRun, setLastRun] = useState<Action | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const termRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (!running) return;
    const start = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 500);
    return () => clearInterval(t);
  }, [running]);

  useEffect(() => {
    const el = termRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [output]);

  async function run(label: string, body: Action) {
    if (running) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(label);
    setExitCode(null);
    setElapsed(0);
    setLastRun(body);
    setOutput("");
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        setOutput(`error: ${err.error}\n`);
        setExitCode(1);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let text = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        const m = text.match(EXIT);
        setOutput(m ? text.replace(EXIT, "") : text);
        if (m) setExitCode(Number(m[1]));
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        setOutput((o) => o + "\nstopped.\n");
        setExitCode(130);
      } else {
        setOutput((o) => o + `\n${(e as Error).message}\n`);
        setExitCode(1);
      }
    } finally {
      setRunning(null);
      abortRef.current = null;
      router.refresh();
    }
  }

  const busy = running !== null;
  const ready = status.hasVenv && status.hasGraph;

  const resultLink =
    exitCode === 0 && lastRun
      ? lastRun.action === "slice"
        ? `/slices/${lastRun.cutoff}${lastRun.ablation && lastRun.ablation !== "full system" ? `?ablation=${encodeURIComponent(lastRun.ablation)}` : ""}`
        : lastRun.action === "heldout"
          ? `/slices/${lastRun.cutoff}`
          : lastRun.action === "run-all"
            ? `/slices/${primary}`
            : null
      : null;

  // What the main button runs, shown before anything is pressed.
  const preview = `hindcast slice --cutoff ${cutoff} --ablation "${ablation}"`;

  return (
    <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))", gap: 12, alignItems: "start" }}>
      <div className="steps">
        <section className="tile">
          <h2 className="tile-label">
            <span>
              <span className="step-n">1</span>Setup
            </span>
            {ready && <span style={{ color: "var(--ok)" }}>ready</span>}
          </h2>
          <div className="envbar">
            <span className={status.hasVenv ? "ok" : "missing"}>{status.hasVenv ? "✓" : "○"} Python</span>
            <span className={status.hasGraph ? "ok" : "missing"}>{status.hasGraph ? "✓" : "○"} Graph</span>
            <span className={status.hasResults ? "ok" : "muted"}>{status.hasResults ? "✓" : "○"} Results</span>
            {ready && (
              <span style={{ marginLeft: "auto", display: "flex", gap: 14 }}>
                <button className="linkish small" disabled={busy} onClick={() => run("setup", { action: "setup" })}>
                  Reinstall
                </button>
                <button className="linkish small" disabled={busy} onClick={() => run("build", { action: "build" })}>
                  Rebuild graph
                </button>
              </span>
            )}
          </div>
          {!status.hasVenv && (
            <div className="actions">
              <button className="button" disabled={busy} onClick={() => run("setup", { action: "setup" })}>
                Install Python packages
              </button>
              <span className="small muted">Once, with uv.</span>
            </div>
          )}
          {status.hasVenv && !status.hasGraph && (
            <div className="actions">
              <button className="button" disabled={busy} onClick={() => run("build", { action: "build" })}>
                Build the graph
              </button>
              <span className="small muted">Under a minute, offline.</span>
            </div>
          )}
        </section>

        <section className="tile" style={{ opacity: ready ? 1 : 0.5 }}>
          <h2 className="tile-label">
            <span>
              <span className="step-n">2</span>Run one forecast
            </span>
            <span>about 20 s</span>
          </h2>
          <div className="control-group">
            <span className="control-label">Cutoff</span>
            <div className="segmented lg" role="group" aria-label="Cutoff">
              {slices.map((s) => (
                <button key={s} type="button" aria-pressed={cutoff === s} onClick={() => setCutoff(s)}>
                  {s.slice(0, 4)}
                </button>
              ))}
            </div>
            <span className="control-label" style={{ marginTop: 8 }}>
              Variant
            </span>
            <select value={ablation} onChange={(e) => setAblation(e.target.value)} aria-label="Variant" style={{ maxWidth: 320 }}>
              {ablations.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
          <div className="actions">
            <button
              className="button"
              disabled={busy || !ready}
              onClick={() => run(`${cutoff.slice(0, 4)} · ${ablation}`, { action: "slice", cutoff, ablation })}
            >
              Run the forecast
            </button>
            <button
              className="button ghost"
              disabled={busy || !ready}
              title="Hides each reportable gene’s measurements in turn and checks it can still be reached."
              onClick={() => run(`held-out ${cutoff.slice(0, 4)}`, { action: "heldout", cutoff })}
            >
              Held-out test
            </button>
          </div>
        </section>

        <section className="tile">
          <h2 className="tile-label">
            <span>
              <span className="step-n">3</span>Check everything
            </span>
          </h2>
          <dl className="actions-list">
            <div>
              <dt>
                Tests<span>Includes the attempts to leak future data into a slice.</span>
              </dt>
              <dd>
                <button className="button ghost sm" disabled={busy || !status.hasVenv} onClick={() => run("tests", { action: "verify" })}>
                  Run
                </button>
              </dd>
            </div>
            <div>
              <dt>
                Every cutoff and variant<span>Several minutes.</span>
              </dt>
              <dd>
                <button className="button ghost sm" disabled={busy || !ready} onClick={() => run("run-all", { action: "run-all" })}>
                  Run
                </button>
              </dd>
            </div>
            <div>
              <dt>
                Scorecard<span>The table in the README, from the result files.</span>
              </dt>
              <dd>
                <button className="button ghost sm" disabled={busy || !status.hasVenv} onClick={() => run("scorecard", { action: "scorecard" })}>
                  Print
                </button>
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <div style={{ position: "sticky", top: 80 }}>
        <div className="terminal-bar">
          <div className="small" style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {running ? (
              <>
                <span className="pulse" aria-hidden /> Running <b>{running}</b> <span className="muted mono">{elapsed}s</span>
              </>
            ) : exitCode === null ? (
              <span className="tile-label">Output</span>
            ) : exitCode === 0 ? (
              <span className="tag ok">finished</span>
            ) : (
              <span className="tag bad">exit {exitCode}</span>
            )}
            {resultLink && !running && (
              <Link className="go" href={resultLink}>
                See the results
              </Link>
            )}
          </div>
          {running && (
            <button className="button ghost sm" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          )}
        </div>
        <pre className="terminal" ref={termRef} aria-live="polite">
          {output || (
            <span className="dim">
              <span className="prompt">$</span> {ready ? preview : "waiting for setup"}
              {"\n\n"}
              {ready && "Press Run the forecast. The result opens from a link above when it finishes."}
            </span>
          )}
        </pre>
        <p className="small muted" style={{ marginTop: 12 }}>
          Runs rewrite <code>eval/results/</code> and <code>trajectories/</code>; <code>git checkout -- eval trajectories</code> restores
          them.
        </p>
      </div>
    </div>
  );
}
