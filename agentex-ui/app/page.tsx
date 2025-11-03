import { connection } from 'next/server';

import { AgentexUIRoot } from '@/app/agentex-ui-root';

export default async function RootPage() {
  await connection();

  const sgpAppURL = process.env.NEXT_PUBLIC_SGP_APP_URL ?? '';
  const agentexAPIBaseURL =
    process.env.NEXT_PUBLIC_AGENTEX_API_BASE_URL ?? 'http://localhost:5003';

  if (!agentexAPIBaseURL) {
    return (
      <div role="alert">
        <p>Missing some configs</p>
        <pre>{JSON.stringify({ sgpAppURL, agentexAPIBaseURL }, null, 2)}</pre>
      </div>
    );
  }

  return (
    <AgentexUIRoot
      sgpAppURL={sgpAppURL}
      agentexAPIBaseURL={agentexAPIBaseURL}
    />
  );
}
