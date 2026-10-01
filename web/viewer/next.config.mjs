/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Shared contracts ship as TypeScript source from the workspace, not as a build.
  transpilePackages: ["@stage-gen/ui"],
  // `next dev` would otherwise write AGENTS.md and CLAUDE.md into this folder on every
  // start; `stage-gen view` starts it, and it must leave the checkout as it found it.
  agentRules: false,
};

export default nextConfig;
