import { connection } from 'next/server';

import { AgentexUIRoot } from '@/components/agentex-ui-root';
import { AgentexProvider } from '@/components/providers';

export default async function RootPage() {
  await connection();

  const sgpAppURL = process.env.NEXT_PUBLIC_SGP_APP_URL ?? '';
  // The account picker needs the platform API (accounts come from /api/user-info).
  const accountsEnabled = !!(
    process.env.SGP_API_URL ?? process.env.NEXT_PUBLIC_SGP_APP_URL
  );

  return (
    <AgentexProvider accountsEnabled={accountsEnabled} sgpAppURL={sgpAppURL}>
      <AgentexUIRoot />
    </AgentexProvider>
  );
}
