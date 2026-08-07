import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Needed for web/Dockerfile.railway's slim multi-stage runtime image
  // (.next/standalone + .next/static). No effect on `next dev`.
  output: "standalone",
};

export default nextConfig;
