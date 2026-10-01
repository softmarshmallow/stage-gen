/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Shared contracts ship as TypeScript source from the workspace, not as a build.
  transpilePackages: ["@stage-gen/ui"],
};

export default nextConfig;
