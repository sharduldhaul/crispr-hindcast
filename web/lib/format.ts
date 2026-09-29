// Plain-language labels for the pipeline's internal vocabulary.

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

export function year(cutoff: string): string {
  return cutoff.slice(0, 4);
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
