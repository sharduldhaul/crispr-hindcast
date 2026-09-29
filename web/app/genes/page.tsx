import type { Metadata } from "next";

import { GeneSearch } from "@/components/GeneSearch";
import { geneIndex } from "@/lib/repo";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Genes" };

export default function GenesPage() {
  const genes = geneIndex();
  return (
    <div className="wrap page">
      <div className="eyebrow">Genes</div>
      <h1>Look up a gene.</h1>
      <p className="lede" style={{ marginTop: 18, marginBottom: 36 }}>
        Every gene the system weighed, planted as a trap, or that appears in the answer key. Open one
        to see what the system said about it at each cutoff, and when the field actually found it.
      </p>
      <GeneSearch genes={genes} />
    </div>
  );
}
