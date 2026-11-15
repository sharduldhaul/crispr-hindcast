import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page reads the repository's result files at request time, so a
  // re-run from the Run page shows up on the next page load without a rebuild.
  reactStrictMode: true,
  // The files the pages read live outside web/. A hosted deployment ships only
  // traced files, so the trace starts at the repository root and names them.
  outputFileTracingRoot: path.join(__dirname, ".."),
  outputFileTracingIncludes: {
    "/**": ["../eval/results/**/*.json", "../eval/rulebook/*.json", "../eval/scorecard.md", "../*.md"],
  },
};

export default nextConfig;
