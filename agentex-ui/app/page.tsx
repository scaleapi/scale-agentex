import { connection } from 'next/server';

import { AgentexUIRoot } from '@/components/agentex-ui-root';
import { AgentexProvider } from '@/components/providers';
import { parseBooleanEnv } from '@/lib/env-utils';

export default async function RootPage() {
  await connection();

  const sgpAppURL = process.env.NEXT_PUBLIC_SGP_APP_URL ?? '';
  const authEnabled = !!process.env.AGENTEX_UI_AUTH_PROVIDER_ID;
  const agentRunSchedulesEnabled = parseBooleanEnv(
    process.env.ENABLE_AGENT_RUN_SCHEDULES,
    'ENABLE_AGENT_RUN_SCHEDULES'
  );
  // The account picker needs the platform API (accounts come from /api/user-info).
  const accountsEnabled = !!(
    process.env.SGP_API_URL ?? process.env.NEXT_PUBLIC_SGP_APP_URL
  );

  return (
    <AgentexProvider
      authEnabled={authEnabled}
      accountsEnabled={accountsEnabled}
      sgpAppURL={sgpAppURL}
    >
      <AgentexUIRoot agentRunSchedulesEnabled={agentRunSchedulesEnabled} />
    </AgentexProvider>
  );
}
