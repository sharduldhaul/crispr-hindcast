import "server-only";

import fs from "node:fs";
import path from "node:path";

import type {
  Establishment,
  HeldoutReport,
  Ingestion,
  Policy,
  SliceResult,
} from "./types";

// The web app lives in web/ inside the repository and reads the pipeline's
// files in place. HINDCAST_ROOT overrides this when the app runs elsewhere.
export const REPO_ROOT = process.env.HINDCAST_ROOT
  ? path.resolve(process.env.HINDCAST_ROOT)
  : path.resolve(process.cwd(), "..");

const RESULTS_DIR = path.join(REPO_ROOT, "eval", "results");
const RULEBOOK_DIR = path.join(REPO_ROOT, "eval", "rulebook");

// Mirrors hindcast.scope and hindcast.pipeline.ABLATIONS.
export const SLICES = ["2014-12-31", "2017-12-31", "2020-12-31"] as const;
export const PRIMARY_SLICE = "2017-12-31";
export const ABLATIONS = [
  "full system",
  "no belief revision",
  "no graph",
  "no method signature",
  "no ontology normalization",
] as const;

export function isSlice(value: string): value is (typeof SLICES)[number] {
  return (SLICES as readonly string[]).includes(value);
}

export function isAblation(value: string): value is (typeof ABLATIONS)[number] {
  return (ABLATIONS as readonly string[]).includes(value);
}

function readJson<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  } catch {
    return null;
  }
}

export function runId(cutoff: string, ablation: string): string {
  return `${cutoff}_${ablation.replaceAll(" ", "-")}`;
}

export function loadSlice(cutoff: string, ablation = "full system"): SliceResult | null {
  return readJson<SliceResult>(path.join(RESULTS_DIR, `${runId(cutoff, ablation)}.json`));
}

export function loadHeldout(cutoff: string): HeldoutReport | null {
  return readJson<HeldoutReport>(path.join(RESULTS_DIR, `heldout_${cutoff}.json`));
}

export function loadIngestion(): Ingestion | null {
  return readJson<Ingestion>(path.join(RESULTS_DIR, "ingestion.json"));
}

export function loadPolicy(): Policy | null {
  return readJson<Policy>(path.join(RULEBOOK_DIR, "policy.json"));
}

export function loadRulebook(): Record<string, Establishment> {
  return readJson<Record<string, Establishment>>(
    path.join(RULEBOOK_DIR, "gene_establishment.json"),
  ) ?? {};
}

export function resultsModifiedAt(): Date | null {
  try {
    const times = fs
      .readdirSync(RESULTS_DIR)
      .filter((f) => f.endsWith(".json"))
      .map((f) => fs.statSync(path.join(RESULTS_DIR, f)).mtimeMs);
    return times.length ? new Date(Math.max(...times)) : null;
  } catch {
    return null;
  }
}

export interface EnvironmentStatus {
  repoRoot: string;
  hasVenv: boolean;
  hasGraph: boolean;
  hasResults: boolean;
}

export function environmentStatus(): EnvironmentStatus {
  return {
    repoRoot: REPO_ROOT,
    hasVenv: fs.existsSync(path.join(REPO_ROOT, ".venv", "bin", "hindcast")),
    hasGraph: fs.existsSync(path.join(REPO_ROOT, "data", "work", "graph.db")),
    hasResults: fs.existsSync(path.join(RESULTS_DIR, `${runId(PRIMARY_SLICE, "full system")}.json`)),
  };
}

// The documents a reader can open from the Docs page, in reading order.
export const DOCS = [
  { slug: "limitations", file: "LIMITATIONS.md", title: "Limitations", blurb: "What the numbers do not mean, in plain language." },
  { slug: "methodology", file: "METHODOLOGY.md", title: "Methodology", blurb: "Every weight and update rule, with its reason." },
  { slug: "data-sources", file: "DATA_SOURCES.md", title: "Data sources", blurb: "Where each record came from and its license." },
  { slug: "schema", file: "SCHEMA.md", title: "Schema", blurb: "The graph: node types, edge types, provenance." },
  { slug: "scorecard", file: "eval/scorecard.md", title: "Scorecard", blurb: "The raw rendered scorecard tables." },
] as const;

export function loadDoc(slug: string): { title: string; body: string } | null {
  const doc = DOCS.find((d) => d.slug === slug);
  if (!doc) return null;
  try {
    return { title: doc.title, body: fs.readFileSync(path.join(REPO_ROOT, doc.file), "utf8") };
  } catch {
    return null;
  }
}

// Every gene the answer key dates, for the timeline.
export function timelineGenes(): { symbol: string; date: string; core: boolean }[] {
  return Object.values(loadRulebook())
    .filter((e) => e.established && e.establishing_record)
    .map((e) => ({
      symbol: e.symbol,
      date: e.establishing_record!.date.slice(0, 10),
      core: e.core_scope,
    }));
}

// What the full system said about one gene at one slice.
export type GeneVerdict =
  | { kind: "forecast"; rank: number; costRank: number; confidence: number; modality: string; statement: string; evidence: number }
  | { kind: "refused"; confidence: number; reason: string; evidence: number }
  | { kind: "already-known" }
  | { kind: "not-considered" };

export interface GeneSliceView {
  cutoff: string;
  verdict: GeneVerdict;
  inGroundTruth: boolean;
  traps: SliceResult["scorecard"]["traps"];
  holdout: HeldoutReport["holdouts"][number] | null;
}

export function geneAcrossSlices(symbol: string): GeneSliceView[] {
  return SLICES.map((cutoff) => {
    const result = loadSlice(cutoff);
    const heldout = loadHeldout(cutoff);
    let verdict: GeneVerdict = { kind: "not-considered" };
    if (result) {
      const item = result.forecast.items.find((i) => i.gene_symbol === symbol);
      const refusal = result.forecast.refusals.find((r) => r.gene_symbol === symbol);
      if (item) {
        verdict = {
          kind: "forecast",
          rank: item.rank_by_confidence,
          costRank: item.rank_by_cost_impact,
          confidence: item.confidence,
          modality: item.implied_modality,
          statement: item.statement,
          evidence: item.evidence_count,
        };
      } else if (refusal) {
        verdict = {
          kind: "refused",
          confidence: refusal.confidence,
          reason: refusal.reason,
          evidence: refusal.evidence_count,
        };
      } else if (result.forecast.already_established.includes(symbol)) {
        verdict = { kind: "already-known" };
      }
    }
    return {
      cutoff,
      verdict,
      inGroundTruth: result?.scorecard.ground_truth_symbols.includes(symbol) ?? false,
      traps: result?.scorecard.traps.filter((t) => t.gene_symbol === symbol) ?? [],
      holdout: heldout?.holdouts.find((h) => h.gene_symbol === symbol) ?? null,
    };
  });
}

// Every gene the interface has something to say about, with a one-line summary.
export interface GeneIndexEntry {
  symbol: string;
  forecastAt: string[];
  groundTruthAt: string[];
  trapped: boolean;
  established: string | null;
}

export function geneIndex(): GeneIndexEntry[] {
  const rulebook = loadRulebook();
  const entries = new Map<string, GeneIndexEntry>();
  const get = (symbol: string) => {
    let e = entries.get(symbol);
    if (!e) {
      e = {
        symbol,
        forecastAt: [],
        groundTruthAt: [],
        trapped: false,
        established: rulebook[symbol]?.establishing_record?.date?.slice(0, 10) ?? null,
      };
      entries.set(symbol, e);
    }
    return e;
  };
  for (const symbol of Object.keys(rulebook)) get(symbol);
  for (const cutoff of SLICES) {
    const result = loadSlice(cutoff);
    if (!result) continue;
    for (const item of result.forecast.items) get(item.gene_symbol).forecastAt.push(cutoff);
    for (const r of result.forecast.refusals) get(r.gene_symbol);
    for (const s of result.scorecard.ground_truth_symbols) get(s).groundTruthAt.push(cutoff);
    for (const t of result.scorecard.traps) get(t.gene_symbol).trapped = true;
  }
  return [...entries.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
}
