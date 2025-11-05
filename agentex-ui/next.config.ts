import type { NextConfig } from 'next';
import path from 'path';

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
  serverExternalPackages: ['better-sqlite3'],
  outputFileTracingRoot: path.join(__dirname, '../../'),
};

export default nextConfig;
