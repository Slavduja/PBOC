/** @type {import('next').NextConfig} */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  // When STATIC_EXPORT is set (Netlify / GitHub Pages), emit a static site to ./out
  output: process.env.STATIC_EXPORT ? "export" : undefined,
  images: { unoptimized: true },
  // Set for GitHub project sites served under /<repo> (empty for Netlify / root)
  basePath: basePath || undefined,
  assetPrefix: basePath || undefined,
  trailingSlash: true,
};

export default nextConfig;
