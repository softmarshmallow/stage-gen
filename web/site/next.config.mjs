/** @type {import('next').NextConfig} */
const nextConfig = {
  // A static export: every page is HTML on disk, served by `scripts/site.py serve` or any
  // file server. Pages read only the staged catalog and example media under .catalog/ and
  // public/examples/, which `scripts/site.py build` writes before `next build` runs.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  // A copy served below a folder (for example a presentation's showcase-site/) sets
  // SITE_BASE_PATH at build time; lib/media.ts prefixes media URLs with the same value.
  basePath: process.env.SITE_BASE_PATH ?? "",
  reactStrictMode: true,
  // Shared contracts and players ship as TypeScript source from the workspace.
  transpilePackages: ["@stage-gen/ui"],
  // `next dev` would otherwise write AGENTS.md and CLAUDE.md into this folder.
  agentRules: false,
};

export default nextConfig;
