import type { Metadata } from "next";
import Link from "next/link";

import { DOCS } from "@/lib/repo";

export const metadata: Metadata = { title: "Docs" };

export default function DocsIndex() {
  return (
    <div className="wrap page">
      <div className="eyebrow">Docs</div>
      <h1>The fine print, in full.</h1>
      <p className="lede" style={{ marginTop: 18, marginBottom: 36 }}>
        The repository documents every decision. Start with the limitations: they say what each
        number does and does not mean.
      </p>
      <div className="grid grid-3">
        {DOCS.map((d, i) => (
          <Link key={d.slug} href={`/docs/${d.slug}`} className={`card lift rise rise-${i + 1}`}>
            <div className="eyebrow">{d.file}</div>
            <h3>{d.title}</h3>
            <p className="small muted">{d.blurb}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
