import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";

import { ABLATIONS, REPO_ROOT, SLICES, isAblation, isSlice } from "@/lib/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// One pipeline job at a time: runs write the same database and result files.
const state = globalThis as unknown as { __hindcastJob?: { label: string; started: number } | null };

interface Plan {
  label: string;
  command: string;
  args: string[];
}

const HINDCAST = path.join(REPO_ROOT, ".venv", "bin", "hindcast");

/** Turn a request body into a fixed, validated command. Nothing from the body reaches a shell. */
function plan(body: unknown): Plan | { error: string } {
  if (!body || typeof body !== "object") return { error: "expected a JSON body" };
  const { action, cutoff, ablation } = body as Record<string, unknown>;
  const needCutoff = () => (typeof cutoff === "string" && isSlice(cutoff) ? cutoff : null);

  switch (action) {
    case "setup":
      return {
        label: "set up the Python environment",
        command: "sh",
        args: ["-c", 'uv venv --python 3.12 .venv && uv pip install -e ".[dev]"'],
      };
    case "build":
      return { label: "build the graph", command: HINDCAST, args: ["build"] };
    case "slice": {
      const c = needCutoff();
      if (!c) return { error: `cutoff must be one of ${SLICES.join(", ")}` };
      const a = typeof ablation === "string" ? ablation : "full system";
      if (!isAblation(a)) return { error: `ablation must be one of ${ABLATIONS.join(", ")}` };
      return { label: `run ${c} (${a})`, command: HINDCAST, args: ["slice", "--cutoff", c, "--ablation", a] };
    }
    case "heldout": {
      const c = needCutoff();
      if (!c) return { error: `cutoff must be one of ${SLICES.join(", ")}` };
      return { label: `held-out test at ${c}`, command: HINDCAST, args: ["heldout", "--cutoff", c] };
    }
    case "run-all":
      return { label: "run every slice and ablation", command: HINDCAST, args: ["run-all"] };
    case "scorecard":
      return { label: "render the scorecard", command: HINDCAST, args: ["scorecard"] };
    case "verify":
      return { label: "run the test suite", command: HINDCAST, args: ["verify"] };
    default:
      return { error: "unknown action" };
  }
}

export function GET() {
  return Response.json({ running: state.__hindcastJob ?? null });
}

export async function POST(request: Request) {
  // The server binds to localhost, but a page on another origin could still
  // post to it from the reader's browser. Refuse anything cross-origin.
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== request.headers.get("host")) {
    return Response.json({ error: "cross-origin request refused" }, { status: 403 });
  }

  const p = plan(await request.json().catch(() => null));
  if ("error" in p) return Response.json({ error: p.error }, { status: 400 });
  if (state.__hindcastJob) {
    return Response.json({ error: `already running: ${state.__hindcastJob.label}` }, { status: 409 });
  }

  const encoder = new TextEncoder();
  let child: ChildProcess | null = null;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let done = false;
      const write = (text: string) => {
        if (done) return;
        try {
          controller.enqueue(encoder.encode(text));
        } catch {
          // the reader went away; the abort handler stops the process
        }
      };
      const finish = (code: number | null) => {
        if (done) return;
        write(`\n__HINDCAST_EXIT__ ${code ?? 1}\n`);
        done = true;
        state.__hindcastJob = null;
        try {
          controller.close();
        } catch {}
      };

      state.__hindcastJob = { label: p.label, started: Date.now() };
      write(`$ ${[path.basename(p.command), ...p.args.map((a) => (a.includes(" ") ? `"${a}"` : a))].join(" ")}\n`);

      child = spawn(p.command, p.args, {
        cwd: REPO_ROOT,
        env: {
          ...process.env,
          NO_COLOR: "1",
          TERM: "dumb",
          COLUMNS: "110",
          PYTHONUNBUFFERED: "1",
        },
      });
      child.stdout?.on("data", (d: Buffer) => write(d.toString()));
      child.stderr?.on("data", (d: Buffer) => write(d.toString()));
      child.on("error", (err) => {
        write(
          `\ncould not start ${p.command}: ${err.message}\n` +
            (p.command === HINDCAST ? "Set up the Python environment first (step 1).\n" : ""),
        );
        finish(127);
      });
      child.on("close", (code) => finish(code));

      request.signal.addEventListener("abort", () => child?.kill("SIGTERM"));
    },
    cancel() {
      child?.kill("SIGTERM");
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
