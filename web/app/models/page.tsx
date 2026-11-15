import type { Metadata } from "next";
import Link from "next/link";

import { CITATION_STATUS, LLM_CONDITION, num, rate, recordLink, withInterval, year } from "@/lib/format";
import { LLM_CONDITIONS, PRIMARY_SLICE, SLICES, isSlice, loadLlm, loadSlice } from "@/lib/repo";
import type { LlmResult, Scorecard } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Language model" };

type Search = Promise<{ cutoff?: string }>;

const RULE_BASED = [
  { ablation: "full system", label: "Rule-based system" },
  { ablation: "no graph", label: "Flat literature baseline" },
] as const;

const COLUMNS = [
  { head: "P@5 [95%]", plain: "Precision at 5: genes later established among the 5 highest-confidence claims, over 5. With its bootstrap interval over genes." },
  { head: "MRR [95%]", plain: "Reciprocal rank of the first established gene in the ranking. With its bootstrap interval over genes." },
  { head: "Traps passed", plain: "Traps answered correctly, over all traps for the slice." },
  { head: "Refusal acc", plain: "Genes refused, over the genes the slice holds too little evidence to answer." },
  { head: "ECE", plain: "Expected calibration error over five confidence bins." },
  { head: "Grounded claims [95%]", plain: "Claims citing at least one row the model was given that names the claimed gene, over all claims. It does not test that the row supports the claim." },
  { head: "Fabricated IDs", plain: "Cited IDs that no row has." },
  { head: "Recalled claims", plain: "Claims for a gene established on or after the cutoff that are not grounded, over all claims for such genes." },
];

function scoreCells(card: Scorecard): string[] {
  const ranking = card.ranking_by_confidence;
  const refusals = `${card.refusal_correct}/${card.refusal_total}`;
  return [
    ranking ? withInterval(ranking.precision_at_5, ranking.precision_at_5_interval) : "n/a",
    ranking ? withInterval(ranking.mean_reciprocal_rank, ranking.mean_reciprocal_rank_interval, 3) : "n/a",
    `${card.traps_passed}/${card.traps_total}`,
    card.refusal_accuracy === null ? refusals : `${refusals} (${num(card.refusal_accuracy)})`,
    num(card.expected_calibration_error, 3),
  ];
}

function modelCells(row: LlmResult): string[] {
  const { scorecard, grounding, memorization } = row;
  if (!scorecard || !grounding || !memorization) {
    return COLUMNS.map(() => row.run.status.replace("_", " "));
  }
  const grounded = rate(grounding.grounded_claim_rate, "no claims");
  const interval = grounding.grounded_claim_rate_interval;
  return [
    ...scoreCells(scorecard),
    grounding.grounded_claim_rate.denominator
      ? `${grounded} [${interval.lower.toFixed(2)}, ${interval.upper.toFixed(2)}]`
      : grounded,
    String(grounding.fabricated_ids.length),
    `${memorization.recalled_rate.numerator} of ${memorization.recalled_rate.denominator}`,
  ];
}

function Claims({ row }: { row: LlmResult }) {
  const { scorecard, grounding, memorization } = row;
  if (!scorecard || !grounding || !memorization || !row.run.forecast) {
    return (
      <div className="callout neutral">
        <p>
          <b>{row.run.status === "failed" ? "Failed" : "Not run"}.</b> {row.run.status_reason}
        </p>
      </div>
    );
  }
  const items = new Map(row.run.forecast.items.map((item) => [item.gene_id, item]));
  if (grounding.claims.length === 0) {
    return <p className="muted small">No claims. {row.run.forecast.refusals.length} genes refused.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Gene</th>
            <th className="num">Confidence</th>
            <th>Outcome</th>
            <th>Evidence</th>
            <th>Citations</th>
            <th>Rationale</th>
          </tr>
        </thead>
        <tbody>
          {grounding.claims.map((claim) => {
            const item = items.get(claim.gene_id);
            const cameTrue = scorecard.ground_truth_symbols.includes(claim.gene_symbol);
            const recalled = memorization.recalled_claims.includes(claim.gene_symbol);
            return (
              <tr key={claim.gene_id}>
                <td>
                  <Link href={`/genes/${claim.gene_symbol}`} className="gene">
                    {claim.gene_symbol}
                  </Link>
                </td>
                <td className="num">{num(item?.confidence, 2)}</td>
                <td>{cameTrue ? <span className="tag ok">came true</span> : <span className="tag plain">not confirmed</span>}</td>
                <td>
                  {claim.grounded ? (
                    <span className="tag ok" title="Cites a row the model was given that names this gene.">grounded</span>
                  ) : recalled ? (
                    <span className="tag future" title="Came true, and cites no row the model was given that names this gene.">recalled</span>
                  ) : (
                    <span className="tag plain" title="Cites no row the model was given that names this gene.">not grounded</span>
                  )}
                </td>
                <td>
                  {claim.citations.length === 0 ? (
                    <span className="muted small">none</span>
                  ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {claim.citations.map((c) => {
                        const status = CITATION_STATUS[c.status];
                        const bad = c.status === "fabricated" || c.status === "post_cutoff";
                        const title = `${status.plain} ${c.names_gene ? "Names this gene." : "Does not name this gene."}`;
                        const text = `${c.cited_id} · ${status.label}`;
                        const link = c.status === "fabricated" ? null : recordLink(c.cited_id);
                        return link ? (
                          <a key={c.cited_id} href={link} target="_blank" rel="noreferrer" title={title} className={`tag ${bad ? "bad" : "plain"}`}>
                            {text} ↗
                          </a>
                        ) : (
                          <span key={c.cited_id} title={title} className={`tag ${bad ? "bad" : "plain"}`}>
                            {text}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </td>
                <td className="small" style={{ minWidth: "28ch" }}>
                  {item?.statement}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default async function ModelsPage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const cutoff = sp.cutoff && isSlice(sp.cutoff) ? sp.cutoff : PRIMARY_SLICE;
  const models = LLM_CONDITIONS.flatMap((condition) => {
    const row = loadLlm(cutoff, condition);
    return row ? [{ condition, row }] : [];
  });
  const notRun = models.filter((m) => m.row.run.status === "not_run").length;
  const modelIds = [...new Set(models.map((m) => m.row.run.model_id))];

  return (
    <div className="wrap page">
      <div className="eyebrow">Language model</div>
      <h1>The same question, put to a language model</h1>
      <p className="lede" style={{ marginTop: 18 }}>
        Three conditions: no evidence, retrieved paper titles, and tools over the sealed graph. One grader scores all of them.
      </p>

      <nav className="segmented lg" aria-label="Cutoff" style={{ marginTop: 24 }}>
        {SLICES.map((s) => (
          <Link
            key={s}
            href={`/models?cutoff=${s}`}
            aria-current={s === cutoff ? "true" : undefined}
            title={s === PRIMARY_SLICE ? "The primary slice" : undefined}
          >
            {year(s)}
          </Link>
        ))}
      </nav>

      <section className="section">
        <div className="section-head">
          <h2>Scorecard</h2>
          <p>
            {modelIds.length > 0 && (
              <>
                Model <span className="mono">{modelIds.join(", ")}</span>.{" "}
              </>
            )}
            {notRun > 0 && `${notRun} of ${models.length} model rows have no committed response and are reported as not run.`}
          </p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>System</th>
                {COLUMNS.map((c) => (
                  <th key={c.head} className="num" title={c.plain}>
                    {c.head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {RULE_BASED.map(({ ablation, label }) => {
                const card = loadSlice(cutoff, ablation)?.scorecard;
                if (!card) return null;
                // The rule-based rows cite no IDs, so the last three columns do not apply.
                const cells = [...scoreCells(card), "n/a", "n/a", "n/a"];
                return (
                  <tr key={ablation}>
                    <td>{label}</td>
                    {cells.map((cell, i) => (
                      <td key={COLUMNS[i].head} className="num">
                        {cell}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {models.map(({ condition, row }) => (
                <tr key={condition}>
                  <td title={LLM_CONDITION[condition].plain}>{LLM_CONDITION[condition].label}</td>
                  {modelCells(row).map((cell, i) => (
                    <td key={COLUMNS[i].head} className="num">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <details className="disclose" style={{ marginTop: 14 }}>
          <summary>Column definitions</summary>
          <div className="body">
            <dl className="small">
              {COLUMNS.map((c) => (
                <div key={c.head} style={{ marginBottom: 8 }}>
                  <dt>
                    <b>{c.head}</b>
                  </dt>
                  <dd style={{ margin: 0, color: "var(--ink-2)" }}>{c.plain}</dd>
                </div>
              ))}
            </dl>
            <p className="small">
              <Link href="/docs/methodology">Methodology</Link> gives the full definitions.
            </p>
          </div>
        </details>
      </section>

      {models.map(({ condition, row }) => (
        <section className="section" key={condition}>
          <div className="section-head">
            <h2>{LLM_CONDITION[condition].label}</h2>
            <p>
              {LLM_CONDITION[condition].plain}
              {row.run.status === "ran" &&
                ` ${row.run.input_tokens.toLocaleString("en-US")} input and ${row.run.output_tokens.toLocaleString("en-US")} output tokens, $${row.run.cost_usd.toFixed(2)}.`}
              {row.run.status === "ran" &&
                condition === "graph" &&
                ` ${row.run.tool_calls.length} of ${row.run.tool_call_budget} tool calls used.`}
            </p>
          </div>
          <Claims row={row} />
        </section>
      ))}
    </div>
  );
}
