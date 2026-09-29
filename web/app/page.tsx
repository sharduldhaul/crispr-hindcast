import Link from "next/link";

import { CutoffTimeline } from "@/components/CutoffTimeline";
import { int, num, year } from "@/lib/format";
import {
  PRIMARY_SLICE,
  SLICES,
  environmentStatus,
  loadIngestion,
  loadPolicy,
  loadSlice,
  timelineGenes,
} from "@/lib/repo";

export const dynamic = "force-dynamic";

export default function Home() {
  const slices = SLICES.map((cutoff) => ({ cutoff, result: loadSlice(cutoff) }));
  const ingestion = loadIngestion();
  const policy = loadPolicy();
  const env = environmentStatus();
  const threshold = policy?.refusal.confidence_threshold ?? 0.25;

  return (
    <div className="wrap page">
      {!env.hasResults && (
        <div className="callout" style={{ marginBottom: 32 }}>
          <p>
            No results found under <code>{env.repoRoot}/eval/results</code>. Open{" "}
            <Link href="/run">Run the pipeline</Link> to build the graph and produce them.
          </p>
        </div>
      )}

      {/* ---------- hero ---------- */}
      <section style={{ display: "grid", gap: 28, maxWidth: 900 }}>
        <div className="eyebrow rise">A time-travel test for scientific prediction</div>
        <h1 className="rise rise-1">
          Freeze the evidence at a date.
          <br />
          <em style={{ color: "var(--accent)" }}>Forecast</em> what science finds next.
        </h1>
        <p className="lede rise rise-2">
          This project hides every paper published after a chosen date, asks a reasoning system to
          predict which genes researchers will discover next, then opens the sealed envelope and
          grades the prediction against what the field actually published. It is a fair test of
          whether a machine can see where science is going, not just recite where it has been.
        </p>
        <div className="rise rise-3" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Link className="button" href={`/slices/${PRIMARY_SLICE}`}>
            See the {year(PRIMARY_SLICE)} forecast
          </Link>
          <Link className="button ghost" href="/run">
            Run it yourself
          </Link>
        </div>
      </section>

      {/* ---------- the idea ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>The idea, in plain words</h2>
          <span className="num">01</span>
        </div>
        <div className="grid grid-3">
          <div className="card rise rise-1">
            <div className="eyebrow">The disease</div>
            <h3>A switch babies already have</h3>
            <p>
              Sickle cell disease comes from faulty adult hemoglobin, the protein that carries oxygen
              in blood. Before birth we make a different version, <b>fetal hemoglobin</b>, that does
              not sickle. It switches off after birth. Turn it back on and the disease eases. The
              open question for decades: <i>which genes control that switch?</i>
            </p>
          </div>
          <div className="card rise rise-2">
            <div className="eyebrow">The test</div>
            <h3>Seal the future, then predict it</h3>
            <p>
              Pick a cutoff date, say the end of 2017. The system may only see evidence dated before
              it: genetic studies, lab screens, paper records. It then names the genes it believes the
              field will find next, or says honestly that the evidence is not enough. Everything after
              the cutoff is the answer key.
            </p>
          </div>
          <div className="card rise rise-3">
            <div className="eyebrow">Why it is fair</div>
            <h3>The rules are locked in first</h3>
            <p>
              The hiding is enforced by the database itself, and tests try to break it. The answer key
              is what really got published, not something the author wrote. Every setting was frozen
              and tagged in git <i>before</i> the first run, so nothing was tuned to look good. There
              is no AI language model inside; every decision is a written rule.
            </p>
          </div>
        </div>
      </section>

      {/* ---------- timeline ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>What the system can see, and what it cannot</h2>
          <span className="num">02</span>
        </div>
        <CutoffTimeline genes={timelineGenes()} slices={SLICES} initialCutoff={PRIMARY_SLICE} free />
      </section>

      {/* ---------- results ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>How it did</h2>
          <p>The same test run at three cutoffs. Each opens into the full forecast.</p>
        </div>
        <div className="grid grid-3">
          {slices.map(({ cutoff, result }, i) => {
            const card = result?.scorecard;
            const conf = card?.ranking_by_confidence;
            return (
              <Link key={cutoff} href={`/slices/${cutoff}`} className={`card lift rise rise-${i + 1}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <div className="eyebrow" style={{ margin: 0 }}>
                    Cutoff
                  </div>
                  {cutoff === PRIMARY_SLICE && <span className="tag bad">primary</span>}
                </div>
                <div style={{ fontFamily: "var(--font-display)", fontSize: "3.2rem", lineHeight: 1.05, margin: "6px 0 16px" }}>
                  {year(cutoff)}
                </div>
                {card ? (
                  <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                    <div className="stat">
                      <div className="value">{card.forecast_size}</div>
                      <div className="label">genes predicted</div>
                    </div>
                    <div className="stat future">
                      <div className="value">{card.ground_truth_symbols.length}</div>
                      <div className="label">actually found later</div>
                    </div>
                    <div className="stat accent">
                      <div className="value">
                        {conf?.hits_at_10.length ?? 0}
                        <small>correct</small>
                      </div>
                      <div className="label">predictions that came true</div>
                    </div>
                    <div className="stat">
                      <div className="value">
                        {card.traps_passed}
                        <small>/{card.traps_total}</small>
                      </div>
                      <div className="label">trick questions avoided</div>
                    </div>
                  </div>
                ) : (
                  <p className="muted">Not run yet.</p>
                )}
              </Link>
            );
          })}
        </div>
        <p className="small muted" style={{ marginTop: 18, maxWidth: "75ch" }}>
          The system refuses far more often than it predicts. That is by design: a gene is only named
          if its confidence clears {num(threshold)} and it has real supporting evidence. Saying “the
          evidence is not there yet” about a discovery that had not happened is scored as a correct
          answer.
        </p>
      </section>

      {/* ---------- cost ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Why cost is part of the answer</h2>
          <span className="num">03</span>
        </div>
        <div className="grid grid-2" style={{ alignItems: "start" }}>
          <div>
            <p className="lede" style={{ fontSize: "1.1rem" }}>
              The approved gene therapies for sickle cell cost millions and need a hospital that can
              harvest, edit and return a patient’s own cells. Most people with the disease live where
              that is not available.
            </p>
            <p className="muted">
              So every prediction is also tagged with the kind of treatment it would likely lead to,
              and the forecast is shown twice: ranked by confidence, and re-ranked to favour cheap
              routes such as an ordinary pill. The reordering is shown side by side, not hidden.
            </p>
          </div>
          <div className="grid" style={{ gap: 10 }}>
            {policy &&
              Object.values(policy.cost_lens.price_anchors)
                .sort((a, b) => b.list_price_usd - a.list_price_usd)
                .map((anchor) => (
                  <div
                    key={anchor.brand}
                    className="card"
                    style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "baseline", padding: "14px 18px" }}
                  >
                    <div>
                      <b>{anchor.brand}</b>
                      <div className="small muted">{anchor.target}</div>
                    </div>
                    <div className="mono" style={{ fontSize: "1.2rem", color: anchor.list_price_usd > 100000 ? "var(--accent)" : "var(--ok)" }}>
                      ${int(anchor.list_price_usd)}
                    </div>
                  </div>
                ))}
          </div>
        </div>
      </section>

      {/* ---------- honesty ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Read this before trusting the numbers</h2>
          <span className="num">04</span>
        </div>
        <div className="grid grid-2">
          <div className="callout neutral">
            <p>
              <b>Small and cautious.</b> Two to six genes predicted per cutoff, and exactly one of
              them correct each time. Most genes cannot honestly be called from the evidence available at the time.
            </p>
          </div>
          <div className="callout neutral">
            <p>
              <b>The two big post-2017 discoveries were missed.</b> EIF2AK1 and ZNF410 had almost no
              trace in the open data before 2018, so the system correctly refused, and missed them.
            </p>
          </div>
          <div className="callout neutral">
            <p>
              <b>Two right answers sat just below the line.</b> LIN28B and HDAC2 scored 0.24 against a
              frozen threshold of 0.25. The threshold was not moved after seeing the answer.
            </p>
          </div>
          <div className="callout neutral">
            <p>
              <b>The data is the bottleneck.</b> The lab screens behind the field’s key results are not
              openly available in dated form, so the system mostly sees genetics and paper records.
            </p>
          </div>
        </div>
        <p style={{ marginTop: 18 }}>
          <Link href="/docs/limitations">Read the full limitations →</Link>
        </p>
      </section>

      {/* ---------- explore ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Explore</h2>
          <span className="num">05</span>
        </div>
        <div className="grid grid-4">
          <Link className="card" href={`/slices/${PRIMARY_SLICE}`}>
            <h3>Results</h3>
            <p className="small muted">Each forecast, every refusal with its reason, the trick questions, and calibration.</p>
          </Link>
          <Link className="card" href="/compare">
            <h3>Ablations</h3>
            <p className="small muted">Switch parts of the system off and see what each one is worth.</p>
          </Link>
          <Link className="card" href="/genes">
            <h3>Genes</h3>
            <p className="small muted">Look up any gene: what the system said, and when the field found it.</p>
          </Link>
          <Link className="card" href="/run">
            <h3>Run</h3>
            <p className="small muted">Rebuild the graph, re-run any cutoff, run the tests, live in the browser.</p>
          </Link>
        </div>
        {ingestion && (
          <p className="small muted" style={{ marginTop: 22 }}>
            Built from {int(ingestion.records_available)} public records across BioGRID ORCS, DepMap,
            Open Targets, the GWAS Catalog, Europe PMC, ClinicalTrials.gov, HGNC and Cellosaurus.{" "}
            {int(ingestion.excluded)} were excluded with a recorded reason; {ingestion.spurious} were
            invented. <Link href="/docs/data-sources">Sources and licenses →</Link>
          </p>
        )}
      </section>
    </div>
  );
}
