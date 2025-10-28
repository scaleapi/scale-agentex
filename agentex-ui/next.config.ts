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
};

export default nextConfig;
