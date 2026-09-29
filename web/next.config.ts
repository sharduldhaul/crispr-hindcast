import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page reads the repository's result files at request time, so a
  // re-run from the Run page shows up on the next page load without a rebuild.
  reactStrictMode: true,
};

export default nextConfig;
