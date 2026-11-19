import Link from "next/link";

import { CutoffTimeline } from "@/components/CutoffTimeline";
import { type OutcomeItem, OutcomeDots } from "@/components/viz/OutcomeDots";
import { LLM_CONDITION, year } from "@/lib/format";
import { LLM_CONDITIONS, PRIMARY_SLICE, SLICES, environmentStatus, loadLlm, loadSlice, timelineGenes } from "@/lib/repo";
import type { Rate } from "@/lib/types";

export const dynamic = "force-dynamic";

export default function Home() {
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
        contamination: { numerator: card.contamination_traps_passed, denominator: card.contamination_traps_total },
      },
    };
  });

  // Each model condition summed over the cutoffs it ran at. A cutoff that did
  // not run adds nothing, and `ran` says how many did.
  const models = LLM_CONDITIONS.map((condition) => {
    const rows = SLICES.flatMap((cutoff) => {
      const row = loadLlm(cutoff, condition);
      return row?.scorecard && row.grounding && row.memorization ? [{ ...row, scorecard: row.scorecard, grounding: row.grounding, memorization: row.memorization }] : [];
    });
    const sum = (pick: (r: (typeof rows)[number]) => Rate): Rate => ({
      numerator: rows.reduce((n, r) => n + pick(r).numerator, 0),
      denominator: rows.reduce((n, r) => n + pick(r).denominator, 0),
    });
    return {
      condition,
      ran: rows.length,
      grounded: sum((r) => r.grounding.grounded_claim_rate),
      recalled: sum((r) => r.memorization.recalled_rate),
      contamination: sum((r) => ({
        numerator: r.scorecard.contamination_traps_passed,
        denominator: r.scorecard.contamination_traps_total,
      })),
      fabricated: rows.reduce((n, r) => n + r.grounding.fabricated_ids.length, 0),
    };
  });
  const alone = models.find((m) => m.condition === "none");
  const graph = models.find((m) => m.condition === "graph");
  const fabricated = models.reduce((n, m) => n + m.fabricated, 0);
  const modelRuns = models.reduce((n, m) => n + m.ran, 0);

  const ran = runs.flatMap((r) => (r.result ? [r.result] : []));
  const ruleContamination: Rate = {
    numerator: ran.reduce((n, r) => n + r.contamination.numerator, 0),
    denominator: ran.reduce((n, r) => n + r.contamination.denominator, 0),
  };

  return (
    <div className="wrap page">
      {!env.hasResults && (
        <div className="callout" style={{ marginBottom: 24 }}>
          <p>
            No results found under <code>eval/results</code>. Open <Link href="/run">Reproduce</Link> to build the graph and
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
              Evidence after the cutoff is sealed. A rule-based system and a language model name the genes they expect next and are
              graded against what was published. Each model claim is checked against the evidence it was given: reasoned, or recalled
              from training?
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link className="button" href="/models">
              Reasoned or recalled
            </Link>
            <Link className="button ghost" href={`/slices/${PRIMARY_SLICE}`}>
              {year(PRIMARY_SLICE)} forecast
            </Link>
          </div>
        </section>

        {/* ---------- headline figures ---------- */}
        {alone && alone.ran > 0 && (
          <Link href="/models" className="tile copper half rise rise-1">
            <div className="tile-label">
              Recalled · model alone
              <span className="arrow" aria-hidden>
                ↗
              </span>
            </div>
            <div className="kpi foot">
              {alone.recalled.numerator}
              <small>/ {alone.recalled.denominator}</small>
            </div>
            <p className="sub">correct claims citing nothing it was given</p>
          </Link>
        )}
        {graph && graph.ran > 0 && (
          <Link href="/models" className="tile bone half rise rise-2">
            <div className="tile-label">
              Grounded · with graph tools
              <span className="arrow" aria-hidden>
                ↗
              </span>
            </div>
            <div className="kpi foot">
              {graph.grounded.numerator}
              <small>/ {graph.grounded.denominator}</small>
            </div>
            <p className="sub">
              claims citing a row it was given · {fabricated} fabricated IDs in {modelRuns} runs
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
                <p className="sub">rule-based system · {result.truth.length} genes found later</p>
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

        {/* ---------- traps ---------- */}
        <section className="tile" style={{ "--span": 7 } as React.CSSProperties}>
          <h2 className="tile-label">
            Contamination traps passed
            <Link className="arrow" href={`/slices/${PRIMARY_SLICE}#traps`} aria-label="Traps at the primary cutoff">
              ↗
            </Link>
          </h2>
          <ul className="meters">
            {[
              { label: "Rule-based system", traps: ruleContamination },
              ...models.filter((m) => m.ran > 0).map((m) => ({ label: LLM_CONDITION[m.condition].label, traps: m.contamination })),
            ].map(({ label, traps }) => (
              <li key={label}>
                <span>{label}</span>
                <span className="num">
                  {traps.numerator} of {traps.denominator}
                </span>
                <meter min={0} max={traps.denominator} value={traps.numerator} aria-label={`${label}: ${traps.numerator} of ${traps.denominator}`} />
              </li>
            ))}
          </ul>
          <p className="sub foot">
            Genes established after the cutoff with almost no earlier evidence, over {ran.length} cutoffs. Naming one points to recall.
            The rule-based system rejects them by construction.
          </p>
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
              Recall is a lower bound. <span>A claim that cites a given row can still have been recalled.</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
