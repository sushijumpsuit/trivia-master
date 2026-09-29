import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Build a small self-contained server for the Docker image
  output: "standalone",
};

export default nextConfig;
