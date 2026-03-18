import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: '/agent/:agentName',
        destination: '/?agent_name=:agentName',
        permanent: false,
      },
    ];
  },
  devIndicators: false,
  eslint: {
    // ESLint runs in CI; skip during Docker build to avoid native binding issues
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
