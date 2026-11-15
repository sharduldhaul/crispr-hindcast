import Link from "next/link";

import { CutoffTimeline } from "@/components/CutoffTimeline";
import { type OutcomeItem, OutcomeDots } from "@/components/viz/OutcomeDots";
import { PriceBars } from "@/components/viz/PriceBars";
import { int, modalityLabel, year } from "@/lib/format";
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

  const ran = runs.flatMap((r) => (r.result ? [r.result] : []));
  const trapsPassed = ran.reduce((sum, r) => sum + r.trapsPassed, 0);
  const trapsTotal = ran.reduce((sum, r) => sum + r.trapsTotal, 0);

  return (
    <div className="wrap page">
      {!env.hasResults && (
        <div className="callout" style={{ marginBottom: 24 }}>
          <p>
            No results found under <code>{env.repoRoot}/eval/results</code>. Open <Link href="/run">Run</Link> to build the graph and
            produce them.
          </p>
        </div>
      )}

      <div className="bento">
        {/* ---------- hero ---------- */}
        <section className="tile hero tall rise" style={{ "--span": 8 } as React.CSSProperties}>
          <div className="tile-label">Fetal hemoglobin · sickle cell disease</div>
          <div style={{ display: "grid", gap: 18 }}>
            <h1>
              {/* Each line balances on its own, so "next." never sits alone. */}
              <span style={{ display: "block" }}>Freeze the evidence at a date.</span>
              <span style={{ display: "block" }}>
                <em>Forecast</em> what science finds next.
              </span>
            </h1>
            <p className="lede" style={{ margin: 0 }}>
              Papers after the cutoff are sealed. A rule-based system names the genes it expects next, and is graded against what was
              published.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link className="button" href={`/slices/${PRIMARY_SLICE}`}>
              {year(PRIMARY_SLICE)} forecast
            </Link>
            <Link className="button ghost" href="/run">
              Run it
            </Link>
          </div>
        </section>

        {/* ---------- headline figures ---------- */}
        <Link href={`/slices/${PRIMARY_SLICE}#traps`} className="tile blue half rise rise-1">
          <div className="tile-label">
            Traps avoided
            <span className="arrow" aria-hidden>
              ↗
            </span>
          </div>
          <div className="kpi foot">
            {trapsPassed}
            <small>/ {trapsTotal}</small>
          </div>
          <p className="sub">across {ran.length} cutoffs</p>
        </Link>
        {ingestion && (
          <Link href="/docs#evidence" className="tile bone half rise rise-2">
            <div className="tile-label">
              Public records
              <span className="arrow" aria-hidden>
                ↗
              </span>
            </div>
            <div className="kpi foot">{int(ingestion.records_available)}</div>
            <p className="sub">
              {int(ingestion.excluded)} excluded with a reason · {ingestion.spurious} invented
            </p>
          </Link>
        )}

        {/* ---------- one tile per cutoff ---------- */}
        {runs.map(({ cutoff, result }, i) => (
          <Link key={cutoff} href={`/slices/${cutoff}`} className={`tile rise rise-${i + 1}`}>
            <div className="tile-label">
              <span>
                Cutoff {year(cutoff)}
                {cutoff === PRIMARY_SLICE && " · primary"}
              </span>
              <span className="arrow" aria-hidden>
                ↗
              </span>
            </div>
            {result ? (
              <>
                <div className="kpi">
                  {result.hits}
                  <small>/ {result.predicted} named came true</small>
                </div>
                <div className="foot" aria-label={`${result.hits} of ${result.truth.length} later discoveries foreseen`}>
                  <OutcomeDots items={result.truth} />
                </div>
                <p className="sub">{result.truth.length} genes found later</p>
              </>
            ) : (
              <p className="sub">Not run</p>
            )}
          </Link>
        ))}

        {/* ---------- timeline ---------- */}
        <section className="tile" style={{ "--span": 12 } as React.CSSProperties}>
          <h2 className="tile-label">What the system could see</h2>
          <CutoffTimeline
            genes={timelineGenes()}
            initialCutoff={PRIMARY_SLICE}
            runs={runs.flatMap((r) => (r.result ? [{ cutoff: r.cutoff, predicted: r.result.predicted, hits: r.result.hits }] : []))}
          />
        </section>

        {/* ---------- cost ---------- */}
        <section className="tile" style={{ "--span": 7 } as React.CSSProperties}>
          <h2 className="tile-label">List price by treatment route</h2>
          <PriceBars prices={prices} />
          <p className="sub foot">Each forecast is ranked twice: by confidence, and re-weighted toward cheaper routes.</p>
        </section>

        {/* ---------- limits ---------- */}
        <section className="tile" style={{ "--span": 5 } as React.CSSProperties}>
          <h2 className="tile-label">
            Limits
            <Link className="arrow" href="/docs/limitations" aria-label="Full limitations">
              ↗
            </Link>
          </h2>
          <ul className="plain">
            <li>
              One correct gene per cutoff. <span>Two to six named each time.</span>
            </li>
            <li>
              EIF2AK1 and ZNF410 were missed. <span>Almost no open evidence before 2018.</span>
            </li>
            <li>
              LIN28B and HDAC2 scored 0.24. <span>The frozen threshold is 0.25 and was not moved.</span>
            </li>
            <li>
              Data is the bottleneck. <span>The key lab screens are not open in dated form.</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
