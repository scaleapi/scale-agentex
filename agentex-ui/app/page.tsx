import { connection } from 'next/server';

import { AgentexUIRoot } from '@/components/agentex-ui-root';
import { AgentexProvider } from '@/components/providers';

function parseBooleanEnv(value: string | undefined): boolean {
  if (value === undefined) return false;

  const normalized = value.trim().toLowerCase();
  if (normalized === 'true' || normalized === '1') return true;
  if (normalized === 'false' || normalized === '0') return false;

  throw new Error(`Invalid boolean environment variable value: ${value}`);
}

export default async function RootPage() {
  await connection();

  const sgpAppURL = process.env.NEXT_PUBLIC_SGP_APP_URL ?? '';
  const authEnabled = !!process.env.AGENTEX_UI_AUTH_PROVIDER_ID;
  const agentRunSchedulesEnabled = parseBooleanEnv(
    process.env.ENABLE_AGENT_RUN_SCHEDULES
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
