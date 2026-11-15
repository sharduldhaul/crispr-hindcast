import type { Metadata } from "next";

import { RunConsole } from "@/components/RunConsole";
import { ABLATIONS, HOSTED, PRIMARY_SLICE, SLICES, environmentStatus } from "@/lib/repo";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Run the pipeline" };

const REPOSITORY = "https://github.com/sharduldhaul/crispr-hindcast";

function Hosted() {
  return (
    <div className="wrap page">
      <div className="eyebrow">Run the pipeline</div>
      <h1>Reproduce every number yourself.</h1>
      <p className="lede" style={{ marginTop: 18, marginBottom: 32 }}>
        This site shows the committed results and runs nothing. The pipeline runs from a clone, offline, with no API keys.
      </p>
      <div className="callout neutral" style={{ marginBottom: 32 }}>
        <p>
          <strong>In a browser.</strong> <a href="https://codespaces.new/sharduldhaul/crispr-hindcast">Open the repository in GitHub Codespaces</a>
          . The environment installs itself, builds the graph and starts this app with the Run page enabled.
        </p>
      </div>
      <div className="prose">
        <h2>On your machine</h2>
        <p>
          Needs Python 3.12, uv and Node.js 20.9 or later. The <a href={`${REPOSITORY}#launch-the-app`}>README</a> has the details.
        </p>
        <pre tabIndex={0}>
          {`git clone ${REPOSITORY}.git
cd crispr-hindcast
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
.venv/bin/hindcast build
.venv/bin/hindcast run-all
cd web && npm install && npm run dev`}
        </pre>
      </div>
    </div>
  );
}

export default function RunPage() {
  if (HOSTED) return <Hosted />;
  return (
    <div className="wrap page">
      <div className="eyebrow">Run the pipeline</div>
      <h1>Reproduce every number yourself.</h1>
      <p className="lede" style={{ marginTop: 18, marginBottom: 44 }}>
        Each action runs the command-line tool on this machine, on the committed snapshot, with no API keys.
      </p>
      <RunConsole slices={SLICES} ablations={ABLATIONS} primary={PRIMARY_SLICE} status={environmentStatus()} />
    </div>
  );
}
