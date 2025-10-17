"use client";

import {
  useAgentexRootStore
} from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import type { Agent } from "agentex/resources";

function useSingleAgent(): Agent {
  const agent = useAgentexRootStore((s) => s.agents[0]);
  if (agent === undefined) {
    throw new Error(
      "useSingleAgent must be used within AgentexSingleAgentRoot"
    );
  }
  return agent;
}

export { useSingleAgent };
