"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/slices/2017-12-31", label: "Results", match: "/slices" },
  { href: "/compare", label: "Ablations" },
  { href: "/genes", label: "Genes" },
  { href: "/docs", label: "Docs" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav" aria-label="Main">
      {LINKS.map((link) => {
        const prefix = link.match ?? link.href;
        const active = prefix === "/" ? pathname === "/" : pathname.startsWith(prefix);
        return (
          <Link key={link.href} href={link.href} aria-current={active ? "page" : undefined}>
            {link.label}
          </Link>
        );
      })}
      <Link
        href="/run"
        className="run-link"
        aria-current={pathname.startsWith("/run") ? "page" : undefined}
      >
        Run the pipeline
      </Link>
    </nav>
  );
}
