"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

interface Props {
  slices: readonly string[];
  ablations: readonly string[];
  primary: string;
  status: { hasVenv: boolean; hasGraph: boolean; hasResults: boolean; repoRoot: string };
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
  const [heldoutCutoff, setHeldoutCutoff] = useState(primary);
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

  const disabled = running !== null;
  const needsVenv = !status.hasVenv;
  const needsGraph = !status.hasGraph;

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

  return (
    <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 28, alignItems: "start" }}>
      <div style={{ display: "grid", gap: 14 }}>
        <Step
          n={1}
          title="Set up Python"
          done={status.hasVenv}
          text="Creates .venv and installs the package with uv. Only needed once. You can also do this in a terminal (see the README)."
        >
          <button className="button ghost" disabled={disabled} onClick={() => run("setup", { action: "setup" })}>
            {status.hasVenv ? "Reinstall" : "Install"}
          </button>
        </Step>

        <Step
          n={2}
          title="Build the graph"
          done={status.hasGraph}
          text="Loads the committed data snapshot into a local SQLite graph. Offline, no API keys, under a minute."
        >
          <button className="button ghost" disabled={disabled || needsVenv} onClick={() => run("build", { action: "build" })}>
            {status.hasGraph ? "Rebuild" : "Build"}
          </button>
        </Step>

        <Step n={3} title="Run one cutoff" text="Freeze the evidence at a date and run the whole system once. About 20 seconds.">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={cutoff} onChange={(e) => setCutoff(e.target.value)} aria-label="Cutoff">
              {slices.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select value={ablation} onChange={(e) => setAblation(e.target.value)} aria-label="Variant">
              {ablations.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <button
              className="button"
              disabled={disabled || needsVenv || needsGraph}
              onClick={() => run(`slice ${cutoff}`, { action: "slice", cutoff, ablation })}
            >
              Run
            </button>
          </div>
        </Step>

        <Step n={4} title="Held-out test" text="Hide each reportable gene's measurements in turn and check it can still be reached.">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={heldoutCutoff} onChange={(e) => setHeldoutCutoff(e.target.value)} aria-label="Held-out cutoff">
              {slices.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <button
              className="button ghost"
              disabled={disabled || needsVenv || needsGraph}
              onClick={() => run(`heldout ${heldoutCutoff}`, { action: "heldout", cutoff: heldoutCutoff })}
            >
              Run
            </button>
          </div>
        </Step>

        <Step n={5} title="Run everything" text="Every cutoff and every variant, then the scorecard. Several minutes.">
          <button className="button ghost" disabled={disabled || needsVenv || needsGraph} onClick={() => run("run-all", { action: "run-all" })}>
            Run all
          </button>
        </Step>

        <Step n={6} title="Check it" text="Run the test suite, including the checks that try to leak future data into a slice.">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="button ghost" disabled={disabled || needsVenv} onClick={() => run("verify", { action: "verify" })}>
              Run tests
            </button>
            <button className="button ghost" disabled={disabled || needsVenv} onClick={() => run("scorecard", { action: "scorecard" })}>
              Print scorecard
            </button>
          </div>
        </Step>
      </div>

      <div style={{ position: "sticky", top: 84 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, gap: 12, flexWrap: "wrap" }}>
          <div className="small" style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {running ? (
              <>
                <span className="pulse" aria-hidden /> Running <b>{running}</b> · {elapsed}s
              </>
            ) : exitCode === null ? (
              <span className="muted">Output appears here.</span>
            ) : exitCode === 0 ? (
              <span className="tag ok">finished</span>
            ) : (
              <span className="tag bad">exit {exitCode}</span>
            )}
            {resultLink && !running && <Link href={resultLink}>See the results →</Link>}
          </div>
          {running && (
            <button className="button ghost" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          )}
        </div>
        <pre className="terminal" ref={termRef} aria-live="polite">
          {output || (
            <span className="dim">
              <span className="prompt">$</span> waiting for a command{"\n\n"}
              {`repository: ${status.repoRoot}\n`}
              {`python env: ${status.hasVenv ? "ready" : "missing"}\n`}
              {`graph:      ${status.hasGraph ? "built" : "not built"}\n`}
              {`results:    ${status.hasResults ? "present" : "none yet"}`}
            </span>
          )}
        </pre>
        <p className="small muted" style={{ marginTop: 10 }}>
          Runs rewrite the files in <code>eval/results/</code> and <code>trajectories/</code>. The results
          are deterministic, so only timestamps change; <code>git checkout -- eval trajectories</code> restores
          them.
        </p>
      </div>
    </div>
  );
}

function Step({
  n,
  title,
  text,
  done,
  children,
}: {
  n: number;
  title: string;
  text: string;
  done?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="card lift" style={{ display: "grid", gridTemplateColumns: "40px 1fr", gap: 14 }}>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "1.9rem",
          lineHeight: 1,
          color: done ? "var(--ok)" : "var(--muted)",
        }}
      >
        {done ? "✓" : n}
      </div>
      <div>
        <h3 style={{ fontSize: "1.1rem", marginBottom: 4 }}>{title}</h3>
        <p className="small muted" style={{ marginBottom: 12 }}>
          {text}
        </p>
        {children}
      </div>
    </div>
  );
}
