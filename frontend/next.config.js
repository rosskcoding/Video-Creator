/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  
  // Standalone output for Docker production builds
  output: 'standalone',
  
  eslint: {
    // This repo doesn't ship with an ESLint setup; avoid failing production builds.
    ignoreDuringBuilds: true,
  },
  
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
      },
      {
        // Production: allow images from the same domain via proxy
        protocol: "https",
        hostname: process.env.NEXT_PUBLIC_API_URL 
          ? new URL(process.env.NEXT_PUBLIC_API_URL).hostname 
          : "localhost",
      },
    ],
  },
};

module.exports = nextConfig;

