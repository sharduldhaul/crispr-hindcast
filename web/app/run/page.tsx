import type { Metadata } from "next";

import { RunConsole } from "@/components/RunConsole";
import { ABLATIONS, PRIMARY_SLICE, SLICES, environmentStatus } from "@/lib/repo";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Run the pipeline" };

export default function RunPage() {
  return (
    <div className="wrap page">
      <div className="eyebrow">Run the pipeline</div>
      <h1>Reproduce every number yourself.</h1>
      <p className="lede" style={{ marginTop: 18, marginBottom: 40 }}>
        Each button runs the project’s own command-line tool on this machine and streams its output.
        Nothing is sent anywhere: the data is the committed snapshot, and there are no API keys.
      </p>
      <RunConsole slices={SLICES} ablations={ABLATIONS} primary={PRIMARY_SLICE} status={environmentStatus()} />
    </div>
  );
}
