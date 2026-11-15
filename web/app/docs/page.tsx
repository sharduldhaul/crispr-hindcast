import type { Metadata } from "next";
import Link from "next/link";

import { EvidenceSankey } from "@/components/viz/EvidenceSankey";
import { int } from "@/lib/format";
import { DOCS, loadIngestion } from "@/lib/repo";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Docs" };

export default function DocsIndex() {
  const ingestion = loadIngestion();
  return (
    <div className="wrap page">
      <div className="eyebrow">Docs</div>
      <h1>The fine print, in full.</h1>
      <p className="lede" style={{ marginTop: 18, marginBottom: 40 }}>
        Start with the limitations: what each number does and does not mean.
      </p>
      <div className="grid grid-3">
        {DOCS.map((d, i) => (
          <Link key={d.slug} href={`/docs/${d.slug}`} className={`card rise rise-${Math.min(i + 1, 4)}`}>
            <h3>{d.title}</h3>
            <p className="small muted">{d.blurb}</p>
            <div className="small mono muted" style={{ display: "flex", justifyContent: "space-between", marginTop: 18 }}>
              <span>{d.file}</span>
              <span className="go" />
            </div>
          </Link>
        ))}
      </div>

      {ingestion && (
        <section className="section" id="evidence" style={{ scrollMarginTop: 80 }}>
          <div className="section-head">
            <h2>Where every record went</h2>
            <p>
              {int(ingestion.records_available)} public records · {int(ingestion.excluded)} excluded with a reason · {ingestion.spurious}{" "}
              invented
            </p>
          </div>
          <EvidenceSankey ingestion={ingestion} />
          <p className="small muted" style={{ marginTop: 14 }}>
            Counts are records, not graph nodes. Licenses: <Link href="/docs/data-sources">Data sources</Link>.
          </p>
        </section>
      )}
    </div>
  );
}
