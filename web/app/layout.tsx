import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";

import { Nav } from "@/components/Nav";

import "./globals.css";

const body = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-body",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "CRISPR HINDCAST", template: "%s · CRISPR HINDCAST" },
  description:
    "Freeze the evidence at a date. Forecast what the field finds next. Grade against what it actually found.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${body.variable} ${mono.variable}`}>
      <body>
        <div className="ambient" aria-hidden />
        <header className="masthead">
          <div className="wrap">
            <Link href="/" className="wordmark" aria-label="crispr-hindcast home">
              crispr<span className="bar" aria-hidden />
              <em>hindcast</em>
            </Link>
            <Nav />
          </div>
        </header>
        <main>{children}</main>
        <footer className="footer">
          <div className="wrap">
            <span>Every number traces to a source row.</span>
            <span>Code MIT · each dataset keeps its own license</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
