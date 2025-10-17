'use server';

import { SingleAgent } from '@/entrypoints/single-agent';
import { connection } from 'next/server';

export default async function AgentNamePage({
  params,
}: {
  params: Promise<{ agentName: string }>;
}) {
  const connectionPromise = connection();
  const [{ agentName }] = await Promise.all([params, connectionPromise]);

  const sgpAppURL = process.env.NEXT_PUBLIC_SGP_APP_URL;
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
    <SingleAgent
      agentName={agentName}
      sgpAppURL={sgpAppURL ?? ''}
      agentexAPIBaseURL={agentexAPIBaseURL}
    />
  );
}
