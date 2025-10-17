"use client";

import { useAgentexRootController } from "@/registry/agentex/agentex-root/hooks/use-agentex-root-controller";
import { useSingleAgent } from "@/registry/agentex/agentex-single-agent-root/hooks/use-single-agent";
import type { Task, TaskMessageContent } from "agentex/resources";
import { useMemo } from "react";

type AgentexSingleAgentRootController = {
  createTask: (
    messageContent: TaskMessageContent | null,
    taskParams?: Record<string, unknown> | null
  ) => Promise<Task>;
};

function useAgentexSingleAgentRootController(): AgentexSingleAgentRootController {
  const { createTask } = useAgentexRootController();
  const agent = useSingleAgent();
  const agentID = agent.id;

  return useMemo(
    () => ({
      createTask: (...args) => createTask(agentID, null, ...args),
    }),
    [createTask, agentID]
  );
}

export { useAgentexSingleAgentRootController };
