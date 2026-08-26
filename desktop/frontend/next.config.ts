import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Wails embeds a pre-built static bundle into the Go binary — there is no
  // Node server at runtime, so the frontend must be a static export.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
