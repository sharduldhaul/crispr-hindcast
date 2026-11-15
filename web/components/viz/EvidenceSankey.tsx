"use client";

import * as d3 from "d3";
import { type SankeyLink, type SankeyNode, sankey, sankeyJustify, sankeyLinkHorizontal } from "d3-sankey";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Ingestion } from "@/lib/types";

import { C, DUR, EASE, EASE_IN_OUT, drawIn, fmt, halo, ms, useChart } from "./core";
import { Tooltip } from "./Tooltip";

const SOURCE_NAME: Record<string, string> = {
  europepmc: "Europe PMC",
  depmap: "DepMap",
  biogrid_orcs: "BioGRID ORCS",
  hgnc: "HGNC",
  gwas_catalog: "GWAS Catalog",
  clinicaltrials_gov: "ClinicalTrials.gov",
  cellosaurus: "Cellosaurus",
  opentargets: "Open Targets",
  hindcast_vocabulary: "Vocabulary",
};

const REASON_NAME: Record<string, string> = {
  out_of_scope: "Out of scope",
  malformed_record: "Malformed record",
  unresolved_symbol: "Unresolved gene symbol",
  unresolvable_date: "Undatable",
  unresolved_cell_line: "Unresolved cell line",
};

// Sources smaller than this fold into one node until the reader opens it.
const SMALL = 2000;

type Role = "source" | "group" | "kept" | "graph" | "excluded" | "reason";
type Fold = "small" | "excluded";
interface N {
  id: string;
  name: string;
  role: Role;
  /** The node this one folds into, and grows out of. */
  parent?: string;
  /** Clicking this node opens or folds what it stands for. */
  fold?: Fold;
}
interface L {
  id: string;
  source: string;
  target: string;
  value: number;
  note?: string;
  /** The link this one folds into. */
  parent?: string;
}
type SN = SankeyNode<N, L>;
type SL = SankeyLink<N, L>;
type Box = { x0: number; x1: number; y0: number; y1: number };

const MIN_W = 680;
const H = 460;

/** Build the flow from the ingestion report. Every count balances, open or folded. */
function flows(ing: Ingestion, open: Record<Fold, boolean>): { nodes: N[]; links: L[]; smallCount: number } {
  const available = d3.rollup(
    Object.entries(ing.available_by_source),
    (v) => d3.sum(v, ([, n]) => n),
    ([key]) => key.split(".")[0],
  );
  const nodes: N[] = [];
  const links: L[] = [];
  let admitted = 0;
  let laterExcluded = 0;
  for (const [key, n] of Object.entries(ing.exclusions_by_source)) if (!available.has(key)) laterExcluded += n;
  const sources = [...available].sort((a, b) => b[1] - a[1]);
  const small = sources.filter(([, n]) => n < SMALL);
  const fold = small.length > 1 && !open.small;

  const add = (id: string, name: string, role: Role, total: number, out: number, parent?: string, foldKey?: Fold) => {
    nodes.push({ id, name, role, parent, fold: foldKey });
    if (total - out > 0) links.push({ id: `${id}>kept`, source: id, target: "kept", value: total - out, parent: parent && `${parent}>kept` });
    if (out > 0) links.push({ id: `${id}>excluded`, source: id, target: "excluded", value: out, note: "excluded at intake", parent: parent && `${parent}>excluded` });
    admitted += total - out;
  };
  for (const [key, total] of sources) {
    if (fold && total < SMALL) continue;
    add(`src:${key}`, SOURCE_NAME[key] ?? key, "source", total, ing.exclusions_by_source[key] ?? 0, small.length > 1 && total < SMALL ? "grp:small" : undefined, small.length > 1 && total < SMALL ? "small" : undefined);
  }
  if (fold) {
    add(
      "grp:small",
      `${small.length} smaller sources`,
      "group",
      d3.sum(small, ([, n]) => n),
      d3.sum(small, ([key]) => ing.exclusions_by_source[key] ?? 0),
      undefined,
      "small",
    );
  }
  nodes.push({ id: "kept", name: "Admitted", role: "kept" });
  nodes.push({ id: "graph", name: "In the graph", role: "graph" });
  nodes.push({ id: "excluded", name: "Excluded", role: "excluded", fold: "excluded" });
  links.push({ id: "kept>graph", source: "kept", target: "graph", value: admitted - laterExcluded });
  if (laterExcluded > 0) links.push({ id: "kept>excluded", source: "kept", target: "excluded", value: laterExcluded, note: "dropped while building the graph" });
  if (open.excluded) {
    for (const [key, n] of Object.entries(ing.exclusions_by_reason).sort((a, b) => b[1] - a[1])) {
      nodes.push({ id: `why:${key}`, name: REASON_NAME[key] ?? key.replaceAll("_", " "), role: "reason", parent: "excluded" });
      links.push({ id: `excluded>why:${key}`, source: "excluded", target: `why:${key}`, value: n, parent: "excluded" });
    }
  }
  return { nodes, links, smallCount: small.length };
}

const isExcluded = (l: SL) => (l.target as SN).role === "excluded" || (l.source as SN).role === "excluded";

/**
 * Where every source record went: into the graph, or out with a recorded
 * reason. Nodes marked ⊕ open into what they hold, and fold back.
 */
export function EvidenceSankey({ ingestion }: { ingestion: Ingestion }) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();
  const [open, setOpen] = useState<Record<Fold, boolean>>({ small: false, excluded: true });
  const data = useMemo(() => flows(ingestion, open), [ingestion, open]);
  const prev = useRef<{ nodes: Map<string, Box>; links: Map<string, { d: string; w: number }> }>({ nodes: new Map(), links: new Map() });

  useEffect(() => {
    if (!width || !inView || !svgRef.current) return;
    const W = Math.max(width, MIN_W);
    const entering = !entered.current;
    entered.current = true;
    const duration = ms(DUR.update + 150);

    const layout = sankey<N, L>()
      .nodeId((d) => d.id)
      .nodeAlign(sankeyJustify)
      .nodeWidth(10)
      .nodePadding(16)
      .extent([
        [1, 12],
        [W - 1, H - 12],
      ]);
    const { nodes, links } = layout({ nodes: data.nodes.map((d) => ({ ...d })), links: data.links.map((d) => ({ ...d })) });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const total = d3.sum(nodes.filter((n) => n.role === "source" || n.role === "group"), (n) => n.value ?? 0);
    const linkPath = sankeyLinkHorizontal<N, L>();

    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    if (entering || svg.select(".links").empty()) {
      svg.selectAll("*").remove();
      svg.append("g").attr("class", "links").attr("fill", "none");
      svg.append("g").attr("class", "nodes");
    }

    // Kept flows are the quiet background; the exclusions are the story.
    const color = (l: SL) => (isExcluded(l) ? C.fail : C.ink);
    const rest = (l: SL) => (isExcluded(l) ? 0.55 : 0.11);
    const was = prev.current;

    // ---- links ----
    const link = svg
      .select(".links")
      .selectAll<SVGPathElement, SL>("path")
      .data(links, (d) => d.id)
      .join(
        (enter) =>
          enter
            .append("path")
            // grow out of the folded link it was part of, or from nothing
            .attr("d", (d) => (d.parent && was.links.get(d.parent)?.d) || linkPath(d) || "")
            .attr("stroke-width", (d) => (d.parent && was.links.get(d.parent) ? was.links.get(d.parent)!.w : 0))
            .attr("opacity", entering ? rest : 0),
        (update) => update,
        (exit) => {
          // fold into the link that now stands for it, or thin away
          const into = (d: SL) => (d.parent ? links.find((l) => l.id === d.parent) : undefined);
          return exit
            .transition()
            .duration(duration)
            .ease(EASE_IN_OUT)
            .attr("d", (d) => {
              const p = into(d);
              return p ? linkPath(p) || "" : (was.links.get(d.id)?.d ?? "");
            })
            .attr("stroke-width", (d) => (into(d) ? Math.max(1, into(d)!.width ?? 1) : 0))
            .attr("opacity", 0)
            .remove();
        },
      )
      .style("stroke", color);
    if (entering) {
      link
        .attr("d", (d) => linkPath(d) || "")
        .attr("stroke-width", (d) => Math.max(1, d.width ?? 1))
        .each(function (d) {
          drawIn(d3.select(this), { delay: 200 + ((d.source as SN).depth ?? 0) * 450, duration: 900 });
        });
    } else {
      link
        .transition()
        .duration(duration)
        .ease(EASE_IN_OUT)
        .attr("d", (d) => linkPath(d) || "")
        .attr("stroke-width", (d) => Math.max(1, d.width ?? 1))
        .attr("opacity", rest);
    }

    // ---- nodes ----
    const nodeFill = (n: SN) => (n.role === "excluded" || n.role === "reason" ? C.fail : n.role === "source" || n.role === "group" ? C.ink2 : C.gold);
    const left = (d: SN) => d.x0! < W / 2;
    // On first view a node grows from its own middle; after that, a node
    // that appears grows out of the node it was folded into.
    const startBox = (d: SN): Box => {
      if (entering) return { x0: d.x0!, x1: d.x1!, y0: (d.y0! + d.y1!) / 2, y1: (d.y0! + d.y1!) / 2 };
      const p = d.parent ? (was.nodes.get(d.parent) ?? byId.get(d.parent)) : undefined;
      if (p) return { x0: p.x0!, x1: p.x1!, y0: p.y0!, y1: p.y1! };
      return { x0: d.x0!, x1: d.x1!, y0: d.y0!, y1: d.y1! };
    };
    const node = svg
      .select(".nodes")
      .selectAll<SVGGElement, SN>("g")
      .data(nodes, (d) => d.id)
      .join(
        (enter) => {
          const g = enter
            .append("g")
            .attr("tabindex", 0)
            .style("outline", "none")
            .attr("opacity", entering ? 1 : 0);
          g.append("rect")
            .attr("class", "bar")
            .attr("rx", 2)
            .attr("x", (d) => startBox(d).x0)
            .attr("width", (d) => startBox(d).x1 - startBox(d).x0)
            .attr("y", (d) => startBox(d).y0)
            .attr("height", (d) => Math.max(entering ? 0 : 1.5, startBox(d).y1 - startBox(d).y0));
          g.append("rect").attr("class", "hit").attr("fill", "transparent");
          const text = g
            .append("text")
            .attr("dy", "0.35em")
            .attr("font-size", 12)
            .attr("pointer-events", "none")
            .attr("opacity", entering ? 0 : 1)
            .attr("x", (d) => (left(d) ? startBox(d).x1 + 8 : startBox(d).x0 - 8))
            .attr("y", (d) => (startBox(d).y0 + startBox(d).y1) / 2);
          halo(text, 4);
          text.append("tspan").attr("class", "name").attr("font-weight", (d) => (d.role === "source" ? 400 : 600)).style("fill", C.ink);
          text.append("tspan").attr("class", "count").attr("dx", 6).attr("font-family", "var(--font-mono)").attr("font-size", 11).style("fill", C.muted);
          text.append("tspan").attr("class", "fold").attr("dx", 6).attr("font-size", 12);
          return g;
        },
        (update) => update,
        (exit) => {
          const into = (d: SN) => (d.parent ? byId.get(d.parent) : undefined);
          exit
            .select(".bar")
            .transition()
            .duration(duration)
            .ease(EASE_IN_OUT)
            .attr("x", (d) => into(d)?.x0 ?? d.x0!)
            .attr("y", (d) => into(d)?.y0 ?? d.y0!)
            .attr("height", (d) => (into(d) ? Math.max(1.5, into(d)!.y1! - into(d)!.y0!) : 0));
          return exit.transition().duration(duration).ease(EASE_IN_OUT).attr("opacity", 0).remove();
        },
      );
    node
      .attr("role", (d) => (d.fold ? "button" : "img"))
      .attr("aria-expanded", (d) => (d.fold ? String(open[d.fold]) : null))
      .attr("aria-label", (d) => `${d.name}: ${fmt.int(d.value ?? 0)} records${d.fold ? (open[d.fold] ? ". Press Enter to fold." : ". Press Enter to open.") : ""}`)
      .style("cursor", (d) => (d.fold ? "pointer" : "default"));
    node.select(".bar").style("fill", nodeFill);
    node
      .select(".hit")
      .attr("x", (d) => d.x0! - 6)
      .attr("width", (d) => d.x1! - d.x0! + 12)
      .attr("y", (d) => (d.y0! + d.y1!) / 2 - Math.max(10, (d.y1! - d.y0!) / 2))
      .attr("height", (d) => Math.max(20, d.y1! - d.y0!));
    node.select(".name").text((d) => d.name);
    node.select(".count").text((d) => fmt.int(d.value ?? 0));
    // ⊕ opens what a node stands for; ⊖ folds it. Children fold toward their parent.
    const owner = (d: SN) => d.role === "group" || d.role === "excluded";
    node
      .select(".fold")
      .text((d) => (d.fold && owner(d) ? (open[d.fold] ? "⊖" : "⊕") : d.fold === "small" ? "⊖" : ""))
      .style("fill", (d) => (owner(d) ? C.gold : C.muted));
    const label = node.select<SVGTextElement>("text").attr("text-anchor", (d) => (left(d) ? "start" : "end"));

    if (entering) {
      node
        .select(".bar")
        .transition()
        .delay((d) => ms(100 + (d.depth ?? 0) * 450))
        .duration(ms(700))
        .ease(EASE)
        .attr("y", (d) => d.y0!)
        .attr("height", (d) => Math.max(1.5, d.y1! - d.y0!));
      label
        .attr("x", (d) => (left(d) ? d.x1! + 8 : d.x0! - 8))
        .attr("y", (d) => (d.y0! + d.y1!) / 2)
        .transition()
        .delay((d) => ms(400 + (d.depth ?? 0) * 450))
        .duration(ms(500))
        .attr("opacity", 1);
    } else {
      node.transition().duration(duration).ease(EASE_IN_OUT).attr("opacity", 1);
      node
        .select(".bar")
        .transition()
        .duration(duration)
        .ease(EASE_IN_OUT)
        .attr("x", (d) => d.x0!)
        .attr("width", (d) => d.x1! - d.x0!)
        .attr("y", (d) => d.y0!)
        .attr("height", (d) => Math.max(1.5, d.y1! - d.y0!));
      label
        .transition()
        .duration(duration)
        .ease(EASE_IN_OUT)
        .attr("x", (d) => (left(d) ? d.x1! + 8 : d.x0! - 8))
        .attr("y", (d) => (d.y0! + d.y1!) / 2)
        .attr("opacity", 1);
    }

    prev.current = {
      nodes: new Map(nodes.map((n) => [n.id, { x0: n.x0!, x1: n.x1!, y0: n.y0!, y1: n.y1! }])),
      links: new Map(links.map((l) => [l.id, { d: linkPath(l) || "", w: Math.max(1, l.width ?? 1) }])),
    };

    // ---- hover: trace a flow, or every path through a node ----
    const focus = (keep: (l: SL) => boolean) =>
      link
        .transition("hover")
        .duration(ms(DUR.hover))
        .attr("opacity", (l) => (keep(l) ? (isExcluded(l) ? 0.85 : 0.32) : 0.04));
    const reset = () => {
      link.transition("hover").duration(ms(DUR.hover)).attr("opacity", rest);
      setTip(null);
    };

    link
      .on("pointerenter", function (event: PointerEvent, d) {
        focus((l) => l === d);
        const [px, py] = d3.pointer(event, svgRef.current);
        const src = d.source as SN;
        setTip({
          x: px,
          y: py,
          value: `${fmt.int(d.value)} records`,
          label: `${src.name} → ${(d.target as SN).name}`,
          rows: [{ color: color(d), label: `share of ${src.name}`, value: d3.format(".1%")(d.value / (src.value || 1)) }],
          note: d.note ? `${d.note[0].toUpperCase()}${d.note.slice(1)}.` : undefined,
        });
      })
      .on("pointermove", (event: PointerEvent) => {
        const [px, py] = d3.pointer(event, svgRef.current);
        setTip((t) => (t ? { ...t, x: px, y: py } : t));
      })
      .on("pointerleave", reset);

    const toggle = (d: SN) => {
      if (!d.fold) return;
      setTip(null);
      setOpen((o) => ({ ...o, [d.fold!]: !o[d.fold!] }));
    };
    node
      .on("pointerenter focus", (_e: Event, d) => {
        const touched = new Set<SL>();
        const walk = (n: SN, dir: "in" | "out") => {
          for (const l of (dir === "in" ? n.targetLinks : n.sourceLinks) ?? []) {
            if (touched.has(l)) continue;
            touched.add(l);
            walk((dir === "in" ? l.source : l.target) as unknown as SN, dir);
          }
        };
        walk(d, "in");
        walk(d, "out");
        focus((l) => touched.has(l));
        const out = (d.sourceLinks ?? []).slice().sort((a, b) => b.value - a.value);
        const parts = d.role === "group" ? smallParts(ingestion) : null;
        setTip({
          x: left(d) ? d.x1! + 4 : d.x0! - 4,
          y: (d.y0! + d.y1!) / 2,
          value: `${fmt.int(d.value ?? 0)} records`,
          label: `${d.name} · ${d3.format(".1%")((d.value ?? 0) / total)} of everything considered`,
          rows: parts
            ? parts.map(([name, n]) => ({ label: name, value: fmt.int(n) }))
            : out.slice(0, 4).map((l) => ({ color: color(l), label: `→ ${(l.target as SN).name}`, value: fmt.int(l.value) })),
          note: d.fold
            ? d.role === "group" || d.role === "excluded"
              ? open[d.fold]
                ? "Click to fold."
                : `Click to open${d.role === "excluded" ? " the reasons" : ""}.`
              : "Click to fold back into one node."
            : undefined,
        });
      })
      .on("pointerleave blur", reset)
      .on("click", (_e: Event, d) => toggle(d))
      .on("keydown", (event: KeyboardEvent, d) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggle(d);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, inView, data]);

  return (
    <div>
      <p className="viz-hint" style={{ margin: "0 0 12px" }}>
        Click a node marked <span style={{ color: "var(--accent)" }}>⊕</span> to open it and{" "}
        <span style={{ color: "var(--accent)" }}>⊖</span> to fold it. Hover any flow to trace it.
      </p>
      <div className="viz-frame" style={{ ["--min-w" as string]: `${MIN_W}px`, padding: "8px 0" }}>
        <div className="viz" ref={wrapRef} style={{ minHeight: H }}>
          <svg
            ref={svgRef}
            role="group"
            aria-label={`Flow of ${fmt.int(ingestion.records_available)} source records into the graph or out with a recorded reason`}
          />
          <Tooltip tip={tip} />
        </div>
      </div>
    </div>
  );
}

/** What the folded "smaller sources" node holds, for its tooltip. */
function smallParts(ing: Ingestion): [string, number][] {
  const available = d3.rollup(
    Object.entries(ing.available_by_source),
    (v) => d3.sum(v, ([, n]) => n),
    ([key]) => key.split(".")[0],
  );
  return [...available]
    .filter(([, n]) => n < SMALL)
    .sort((a, b) => b[1] - a[1])
    .map(([key, n]) => [SOURCE_NAME[key] ?? key, n]);
}
