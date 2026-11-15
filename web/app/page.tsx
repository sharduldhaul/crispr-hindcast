import Link from "next/link";

import { CutoffTimeline } from "@/components/CutoffTimeline";
import { type OutcomeItem, OutcomeDots } from "@/components/viz/OutcomeDots";
import { PriceBars } from "@/components/viz/PriceBars";
import { int, modalityLabel, num, year } from "@/lib/format";
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
  const ingestion = loadIngestion();
  const policy = loadPolicy();
  const env = environmentStatus();
  const threshold = policy?.refusal.confidence_threshold ?? 0.25;

  const runs = SLICES.map((cutoff) => {
    const result = loadSlice(cutoff);
    if (!result) return { cutoff, result: null };
    const card = result.scorecard;
    const predicted = new Set(result.forecast.items.map((i) => i.gene_symbol));
    const refused = new Set(result.forecast.refusals.map((r) => r.gene_symbol));
    const truth: OutcomeItem[] = card.ground_truth_symbols.map((s) => ({
      symbol: s,
      kind: predicted.has(s) ? "hit" : refused.has(s) ? "missed" : "none",
    }));
    return {
      cutoff,
      result: {
        predicted: card.forecast_size,
        hits: truth.filter((t) => t.kind === "hit").length,
        truth,
        trapsPassed: card.traps_passed,
        trapsTotal: card.traps_total,
      },
    };
  });

  const prices = policy
    ? Object.entries(policy.cost_lens.price_anchors)
        .sort(([, a], [, b]) => b.list_price_usd - a.list_price_usd)
        .map(([generic, a]) => {
          const isGeneric = a.brand === "several generic";
          return {
            name: isGeneric ? generic[0].toUpperCase() + generic.slice(1) : a.brand,
            sub: isGeneric ? "generic pill, per year, order of magnitude" : a.target,
            price: a.list_price_usd,
            route: modalityLabel(a.modality),
            note: a.note,
            source: a.source,
          };
        })
    : [];

  return (
    <div className="wrap page">
      {!env.hasResults && (
        <div className="callout" style={{ marginBottom: 32 }}>
          <p>
            No results found under <code>{env.repoRoot}/eval/results</code>. Open <Link href="/run">Run</Link> to build the graph and
            produce them.
          </p>
        </div>
      )}

      {/* ---------- hero ---------- */}
      <section style={{ display: "grid", gap: 26, maxWidth: 880, paddingTop: 24 }}>
        <div className="eyebrow rise">A time-travel test for scientific prediction</div>
        <h1 className="rise rise-1">
          {/* Each line balances on its own, so "next." never sits alone. */}
          <span style={{ display: "block" }}>Freeze the evidence at a date.</span>
          <span style={{ display: "block" }}>
            <em style={{ color: "var(--accent)" }}>Forecast</em> what science finds next.
          </span>
        </h1>
        <p className="lede rise rise-2">
          Every paper after a chosen date is sealed away. A reasoning system names the genes it expects researchers to discover next.
          Then the envelope is opened, and the forecast is graded against what the field actually published.
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
      <section className="section grid grid-3">
        <div className="rise rise-1">
          <h3>A switch babies already have</h3>
          <p className="muted" style={{ marginTop: 10 }}>
            Sickle cell disease comes from faulty adult hemoglobin. Before birth we make <b style={{ color: "var(--ink)" }}>fetal hemoglobin</b>,
            which does not sickle, then switch it off. Turning it back on eases the disease. Which genes control that switch?
          </p>
        </div>
        <div className="rise rise-2">
          <h3>Seal the future, then predict it</h3>
          <p className="muted" style={{ marginTop: 10 }}>
            The system sees only genetic studies, lab screens and paper records dated before the cutoff. It names the genes it expects
            next, or says plainly that the evidence is not there yet.
          </p>
        </div>
        <div className="rise rise-3">
          <h3>Locked before the first run</h3>
          <p className="muted" style={{ marginTop: 10 }}>
            The database enforces the seal and tests try to break it. The answer key is the published record. Every threshold was frozen
            in git first. No language model; every decision is a written rule.
          </p>
        </div>
      </section>

      {/* ---------- timeline ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>What the system could see</h2>
          <p>Move the cutoff through time. Everything to its right is sealed away and becomes the answer key.</p>
        </div>
        <CutoffTimeline
          genes={timelineGenes()}
          initialCutoff={PRIMARY_SLICE}
          runs={runs.flatMap((r) => (r.result ? [{ cutoff: r.cutoff, predicted: r.result.predicted, hits: r.result.hits }] : []))}
        />
      </section>

      {/* ---------- results ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>How it did</h2>
          <p>
            A gene is only named if its confidence clears {num(threshold)}. Saying “not yet” about a discovery that had not happened
            scores as a correct answer.
          </p>
        </div>
        <div className="grid grid-3">
          {runs.map(({ cutoff, result }, i) => (
            <Link key={cutoff} href={`/slices/${cutoff}`} className={`card rise rise-${i + 1}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "2.6rem", lineHeight: 1 }}>{year(cutoff)}</span>
                {cutoff === PRIMARY_SLICE && <span className="tag gold">primary</span>}
              </div>
              {result ? (
                <>
                  <p style={{ margin: "18px 0 0", fontSize: "1.05rem" }}>
                    Named <b>{result.predicted}</b> genes. <b style={{ color: "var(--ok)" }}>{result.hits} came true.</b>
                  </p>
                  <div style={{ margin: "14px 0 6px" }} aria-label={`${result.hits} of ${result.truth.length} later discoveries foreseen`}>
                    <OutcomeDots items={result.truth} />
                  </div>
                  <p className="small muted" style={{ margin: 0 }}>
                    of {result.truth.length} genes the field went on to find
                  </p>
                  <div
                    className="small"
                    style={{ display: "flex", justifyContent: "space-between", marginTop: 20, paddingTop: 14, borderTop: "1px solid var(--rule)" }}
                  >
                    <span className="muted">
                      <span style={{ color: "var(--ok)" }}>✓</span> {result.trapsPassed}/{result.trapsTotal} traps avoided
                    </span>
                    <span className="go">Open</span>
                  </div>
                </>
              ) : (
                <p className="muted" style={{ marginTop: 18 }}>
                  Not run yet.
                </p>
              )}
            </Link>
          ))}
        </div>
        <div className="legend" style={{ marginTop: 16 }}>
          <span className="v-hit">
            <span className="dot" /> foreseen
          </span>
          <span className="v-missed">
            <span className="dot ring" /> weighed, then refused
          </span>
          {runs.some((r) => r.result?.truth.some((t) => t.kind === "none")) && (
            <span className="v-none">
              <span className="dot ring" /> no trace before the cutoff
            </span>
          )}
        </div>
      </section>

      {/* ---------- cost ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Why cost is part of the answer</h2>
        </div>
        <div className="grid grid-2" style={{ alignItems: "center", gap: 48 }}>
          <div>
            <p className="lede" style={{ fontSize: "1.1rem" }}>
              The approved gene therapies cost millions and need a hospital that can harvest, edit and return a patient’s own cells. Most
              people with the disease live where that is not available.
            </p>
            <p className="muted">
              So every prediction carries the kind of treatment it would likely lead to, and the forecast is shown twice: by confidence,
              and re-ranked to favour cheap routes such as an ordinary pill.
            </p>
          </div>
          <PriceBars prices={prices} />
        </div>
      </section>

      {/* ---------- honesty ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Read this before trusting the numbers</h2>
          <Link className="go" href="/docs/limitations">
            Full limitations
          </Link>
        </div>
        <div className="grid grid-2" style={{ gap: 28 }}>
          <p style={{ margin: 0 }}>
            <b>Small and cautious.</b> <span className="muted">Two to six genes per cutoff, one correct each time. Most genes cannot honestly be called from the evidence of the day.</span>
          </p>
          <p style={{ margin: 0 }}>
            <b>The two big post-2017 discoveries were missed.</b>{" "}
            <span className="muted">EIF2AK1 and ZNF410 had almost no trace in the open data before 2018, so the system refused, and missed them.</span>
          </p>
          <p style={{ margin: 0 }}>
            <b>Two right answers sat just below the line.</b>{" "}
            <span className="muted">LIN28B and HDAC2 scored 0.24 against a frozen threshold of 0.25. The threshold was not moved after seeing the answer.</span>
          </p>
          <p style={{ margin: 0 }}>
            <b>The data is the bottleneck.</b>{" "}
            <span className="muted">The lab screens behind the field’s key results are not openly available in dated form, so the system mostly sees genetics and paper records.</span>
          </p>
        </div>
        {ingestion && (
          <p className="small muted" style={{ marginTop: 40, paddingTop: 20, borderTop: "1px solid var(--rule)" }}>
            Built from {int(ingestion.records_available)} public records across BioGRID ORCS, DepMap, Open Targets, the GWAS Catalog,
            Europe PMC, ClinicalTrials.gov, HGNC and Cellosaurus. {int(ingestion.excluded)} excluded with a recorded reason;{" "}
            {ingestion.spurious} invented.{" "}
            <Link href="/docs#evidence">See where every record went</Link>
          </p>
        )}
      </section>
    </div>
  );
}
