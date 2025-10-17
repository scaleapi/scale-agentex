"use server";

import { connection } from "next/server";
import { AgentApp } from "@/registry/agentex/quickstart/agent-app";

export default async function AgentNamePage() {
  // load environment variables
  await connection();

  const agentName = process.env.NEXT_PUBLIC_AGENT_NAME;
  const agentexAPIBaseURL = process.env.NEXT_PUBLIC_AGENTEX_API_BASE_URL;

  if (!agentName || !agentexAPIBaseURL) {
    return (
      <div role="alert">
        <p>Missing some environment variables</p>
        <pre>{JSON.stringify({ agentName, agentexAPIBaseURL }, null, 2)}</pre>
      </div>
    );
  }

  return (
    <AgentApp agentName={agentName} agentexAPIBaseURL={agentexAPIBaseURL} />
  );
}
