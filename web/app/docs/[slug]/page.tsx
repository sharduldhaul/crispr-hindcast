import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
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

/** The plain text of a rendered heading. */
function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) {
    return textOf((node.props as { children?: ReactNode }).children);
  }
  return "";
}

/**
 * Heading ids as GitHub writes them, so a link copied from the repository, or
 * written in one doc to another, lands on the same heading here. A repeated
 * heading gets -1, -2, as on GitHub.
 */
function slugger(): (text: string) => string {
  const seen = new Map<string, number>();
  return (text) => {
    const base = text
      .toLowerCase()
      .replace(/[^\p{L}\p{M}\p{N}\p{Pc}\- ]/gu, "")
      .replace(/ /g, "-");
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return count ? `${base}-${count}` : base;
  };
}

const DIAGRAM = /^(?:\.\/)?diagrams\/([a-z_]+\.png)$/;

export default async function DocPage({ params }: { params: Params }) {
  const { slug } = await params;
  const doc = loadDoc(slug);
  if (!doc) notFound();
  const headingId = slugger();

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
            h2: ({ children }) => <h2 id={headingId(textOf(children))}>{children}</h2>,
            h3: ({ children }) => <h3 id={headingId(textOf(children))}>{children}</h3>,
            h4: ({ children }) => <h4 id={headingId(textOf(children))}>{children}</h4>,
            // A diagram is served by this app from diagrams/ (app/diagrams). Any
            // other image would be a third-party request, so it stays a link.
            img: ({ src, alt }) => {
              if (typeof src !== "string") return null;
              const diagram = DIAGRAM.exec(src);
              return diagram ? (
                <img src={`/diagrams/${diagram[1]}`} alt={alt ?? ""} loading="lazy" />
              ) : (
                <a href={rewrite(src).href} target="_blank" rel="noreferrer">
                  Image: {alt}
                </a>
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
