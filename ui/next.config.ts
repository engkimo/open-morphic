import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for Docker production deployment.
  // Produces a self-contained build at .next/standalone with server.js.
  output: "standalone",
};

export default nextConfig;
