import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { DOCS, loadDoc } from "@/lib/repo";

export const dynamic = "force-dynamic";

type Params = Promise<{ slug: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug } = await params;
  return { title: DOCS.find((d) => d.slug === slug)?.title ?? "Docs" };
}

const GITHUB_BLOB = "https://github.com/sharduldhaul/crispr-hindcast/blob/main/";

// Links between the repository's markdown files point at other docs pages;
// links to code point at the file on GitHub.
function rewrite(href: string | undefined): { href: string; external: boolean } {
  if (!href) return { href: "#", external: false };
  if (/^(https?:|mailto:|#)/.test(href)) return { href, external: href.startsWith("http") };
  const clean = href.replace(/^\.\//, "").replace(/^\.\.\//, "");
  const [file, hash] = clean.split("#");
  const doc = DOCS.find((d) => d.file === file || d.file.endsWith(`/${file}`));
  if (doc) return { href: `/docs/${doc.slug}${hash ? `#${hash}` : ""}`, external: false };
  return { href: GITHUB_BLOB + clean, external: true };
}

export default async function DocPage({ params }: { params: Params }) {
  const { slug } = await params;
  const doc = loadDoc(slug);
  if (!doc) notFound();

  return (
    <div className="wrap page">
      <div className="eyebrow">
        <Link href="/docs">Docs</Link> / {doc.title}
      </div>
      <article className="prose">
        <Markdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => {
              const r = rewrite(href);
              return r.external ? (
                <a href={r.href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              ) : (
                <Link href={r.href}>{children}</Link>
              );
            },
          }}
        >
          {doc.body}
        </Markdown>
      </article>
    </div>
  );
}
