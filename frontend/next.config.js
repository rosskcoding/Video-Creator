/** @type {import('next').NextConfig} */

// Safely parse hostname from URL, returns null if invalid
function safeGetHostname(url) {
  if (!url) return null;
  try {
    // Add protocol if missing
    const urlWithProtocol = url.startsWith('http') ? url : `https://${url}`;
    return new URL(urlWithProtocol).hostname;
  } catch {
    // If URL is invalid, try to use it directly as hostname
    return url.split('/')[0].split(':')[0];
  }
}

const nextConfig = {
  reactStrictMode: true,
  
  // Standalone output for Docker production builds
  output: 'standalone',
  
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
        hostname: safeGetHostname(process.env.NEXT_PUBLIC_API_URL) || "localhost",
      },
    ],
  },
};

module.exports = nextConfig;

