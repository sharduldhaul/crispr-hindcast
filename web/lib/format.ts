// Plain-language labels for the pipeline's internal vocabulary.

import type { VerdictKind } from "./types";

// One colour and one word per outcome, used the same way on every page.
export const VERDICT: Record<VerdictKind, { label: string; plain: string }> = {
  hit: { label: "Came true", plain: "Predicted, and the field later confirmed it" },
  forecast: { label: "Predicted", plain: "Predicted, not confirmed by the field" },
  missed: { label: "Missed", plain: "Refused, and the field found it later" },
  refused: { label: "Refused", plain: "The evidence was too thin to make a claim" },
  known: { label: "Known", plain: "Already established before the cutoff" },
  none: { label: "—", plain: "No claim was formed" },
};

export function verdictOf(o: { forecast: boolean; refused: boolean; known: boolean; inTruth: boolean }): VerdictKind {
  if (o.forecast) return o.inTruth ? "hit" : "forecast";
  if (o.refused) return o.inTruth ? "missed" : "refused";
  if (o.known) return "known";
  return "none";
}

export const MODALITY: Record<string, { label: string; plain: string }> = {
  SMALL_MOLECULE: { label: "Small molecule", plain: "a pill or injection, cheap to make at scale" },
  IN_VIVO_EDIT: { label: "In-body gene edit", plain: "an edit delivered inside the body, no cell harvest" },
  EX_VIVO_SINGLE_EDIT: { label: "Ex vivo edit", plain: "cells removed, edited in a lab, and returned, as with Casgevy" },
  EX_VIVO_MULTI_EDIT: { label: "Ex vivo multi-edit", plain: "several edits to harvested cells, the costliest route" },
  NOT_THERAPEUTIC: { label: "Not a therapy", plain: "no plausible treatment route" },
};

export function modalityLabel(code: string | null | undefined): string {
  if (!code) return "none";
  return MODALITY[code]?.label ?? code.toLowerCase().replaceAll("_", " ");
}

export const TRAP_KIND: Record<string, { label: string; plain: string; family: "judgement" | "contamination" }> = {
  association_without_function: {
    label: "Statistical coincidence",
    plain: "A gene that sits near the right spot in the genome but has no plausible role. Endorsing it would mean the system confuses location with cause.",
    family: "judgement",
  },
  pan_essential: {
    label: "Kills every cell",
    plain: "A gene every cell needs to live. Knocking it out changes everything, so it looks like a hit in any screen. It is not a therapy.",
    family: "judgement",
  },
  postdates_cutoff: {
    label: "From the future",
    plain: "A gene the field only found after the cutoff. The right answer is to refuse; claiming it would mean future evidence leaked in.",
    family: "contamination",
  },
};

export function trapLabel(kind: string): string {
  return TRAP_KIND[kind]?.label ?? kind.replaceAll("_", " ");
}

export const ABLATION_PLAIN: Record<string, string> = {
  "full system": "Every component switched on. This is the result the project stands behind.",
  "no belief revision": "Evidence is never weighed. Every claim stays at the starting guess.",
  "no graph": "No reasoning at all: genes ranked by how often papers mention them. The baseline to beat.",
  "no method signature": "Every measurement counts the same, however it was produced.",
  "no ontology normalization": "Gene names are taken as written, without resolving aliases.",
};

export const LLM_CONDITION: Record<string, { label: string; plain: string }> = {
  none: { label: "Model alone", plain: "Given the question and the candidate genes, and no evidence." },
  text: { label: "Model with text retrieval", plain: "Given the five best-matching pre-cutoff paper titles for each gene." },
  graph: { label: "Model with graph tools", plain: "Can query the pre-cutoff graph through a fixed set of read-only tools." },
};

export const CITATION_STATUS: Record<string, { label: string; plain: string }> = {
  in_context: { label: "given", plain: "A row the model was given." },
  out_of_context: { label: "not given", plain: "A real pre-cutoff row the model was not given." },
  post_cutoff: { label: "after cutoff", plain: "A real row dated on or after the cutoff." },
  fabricated: { label: "fabricated", plain: "No row has this ID." },
};

/** A rate with its counts, "0.20 (1 of 5)". `empty` stands in when nothing was counted. */
export function rate(value: { numerator: number; denominator: number }, empty: string): string {
  if (value.denominator === 0) return empty;
  return `${(value.numerator / value.denominator).toFixed(2)} (${value.numerator} of ${value.denominator})`;
}

/** A metric with its bootstrap interval, "0.20 [0.00, 0.60]". */
export function withInterval(value: number, interval: { lower: number; upper: number }, digits = 2): string {
  return `${value.toFixed(digits)} [${interval.lower.toFixed(digits)}, ${interval.upper.toFixed(digits)}]`;
}

export function year(cutoff: string): string {
  return cutoff.slice(0, 4);
}

/** "2017-12-31" as "31 Dec 2017". */
export function longDate(date: string): string {
  const d = new Date(`${date.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** A date as a fractional year, so it can be placed on a time axis. */
export function fractionalYear(date: string): number {
  const d = new Date(`${date.slice(0, 10)}T00:00:00Z`);
  const y = d.getUTCFullYear();
  const start = Date.UTC(y, 0, 1);
  return y + (d.getTime() - start) / (Date.UTC(y + 1, 0, 1) - start);
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "n/a";
  return `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "n/a";
  return value.toFixed(digits);
}

export function int(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return value.toLocaleString("en-US");
}

export function recordLink(id: string): string | null {
  const pub = id.match(/^pub:(\d+)$/);
  if (pub) return `https://europepmc.org/article/MED/${pub[1]}`;
  return null;
}

/**
 * A fractional year read back as words, for cutoffs: the last day of a year is
 * "end of 2017"; anything else is the month it falls in, "Apr 2010".
 */
export function cutoffWords(yr: number): string {
  const y = Math.floor(yr);
  if (yr - y > 0.99) return `end of ${y}`;
  const month = Math.min(11, Math.floor((yr - y) * 12 + 1e-6));
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month]} ${y}`;
}
