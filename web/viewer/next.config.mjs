/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Shared contracts ship as TypeScript source from the workspace, not as a build.
  transpilePackages: ["@stage-gen/ui"],
  // `next dev` would otherwise write AGENTS.md and CLAUDE.md into this folder on every
  // start. It still rewrites the tracked next-env.d.ts to its `.next/dev` form.
  agentRules: false,
};

export default nextConfig;
