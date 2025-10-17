import { useSingleAgent } from "@/registry/agentex/agentex-single-agent-root/hooks/use-single-agent";
import { useAgentexTaskController } from "@/registry/agentex/agentex-task/hooks/use-agentex-task-controller";
import type { TaskMessageContent } from "agentex/resources";
import { useCallback, useMemo } from "react";

type SingleAgentTaskController = {
  isSendMessageEnabled: boolean;
  sendMessage: (content: TaskMessageContent) => Promise<void>;
};

function useSingleAgentTaskController(): SingleAgentTaskController {
  const agentexTaskController = useAgentexTaskController();
  const agent = useSingleAgent();
  const agentID = agent.id;

  const sendMessage = useCallback<SingleAgentTaskController["sendMessage"]>(
    (content) => agentexTaskController.sendMessage(agentID, content),
    [agentexTaskController.sendMessage, agentID]
  );

  return useMemo(
    () => ({
      isSendMessageEnabled: agentexTaskController.isSendMessageEnabled,
      sendMessage,
    }),
    [agentexTaskController.isSendMessageEnabled, sendMessage]
  );
}

export { useSingleAgentTaskController };
