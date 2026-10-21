import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",

  async headers() {
    return [
      {
        source: "/manifest.json",
        headers: [
          { key: "Content-Type", value: "application/manifest+json" },
        ],
      },
    ];
  },

  async rewrites() {
    // Development only: proxy /api/auth, /api/decisions, /api/files to FastAPI.
    // In production Nginx handles routing — no rewrites needed.
    if (process.env.NODE_ENV === "production") return [];
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      // FastAPI-only routes (no equivalent Next.js API route)
      { source: "/api/auth/:path*",      destination: `${apiBase}/api/auth/:path*` },
      { source: "/api/decisions/:path*", destination: `${apiBase}/api/decisions/:path*` },
      { source: "/api/files/:path*",     destination: `${apiBase}/api/files/:path*` },
      { source: "/api/accounts/:path*",  destination: `${apiBase}/api/accounts/:path*` },
    ];
  },
};

export default nextConfig;
