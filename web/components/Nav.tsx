"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/slices/2017-12-31", label: "Results", match: "/slices" },
  { href: "/compare", label: "Ablations" },
  { href: "/models", label: "Model" },
  { href: "/genes", label: "Genes" },
  { href: "/docs", label: "Docs" },
  { href: "/run", label: "Run", className: "run-link" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav" aria-label="Main">
      {LINKS.map((link) => {
        const prefix = link.match ?? link.href;
        const active = prefix === "/" ? pathname === "/" : pathname.startsWith(prefix);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={link.className}
            aria-current={active ? "page" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
