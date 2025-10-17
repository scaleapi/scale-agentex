import { AgentInfo } from "@/components/agent-info";
import { AgentexTaskInfo } from "@/components/agentex-task-info";
import { Skeleton } from "@/components/ui/skeleton";
import { useSafeTheme } from "@/hooks/use-safe-theme";
import { useAgentexTaskController } from "@/registry/agentex/agentex-task/hooks/use-agentex-task-controller";
import {
  useAgentexTask,
  useAgentexTaskAgents,
  useAgentexTaskStore,
} from "@/registry/agentex/agentex-task/hooks/use-agentex-task-store";
import {
  CreateUserMessageDefaultValues,
  CreateUserMessageForm,
  CreateUserMessageFormContent,
  CreateUserMessageFormSelectedAgent,
} from "@/registry/agentex/create-user-message-form/create-user-message-form";
import { MemoizedTaskMessagesComponent } from "@/registry/agentex/task-messages/task-messages";
import { TaskStatusIcon } from "@/registry/agentex/task-status-icon/task-status-icon";
import type { Agent, Task } from "agentex/resources";
import { useEffect, useState } from "react";

function getStorage(): Storage | null {
  return typeof window !== "undefined" ? window.sessionStorage : null;
}

function makeLastSelectedAgentStorageKey(taskID: Task["id"]) {
  return `agentex-task-${taskID}-last-selected-agent`;
}

function saveLastSelectedAgent(
  taskID: Task["id"],
  agentID: Agent["id"],
  storage: Storage
): void {
  if (!taskID) {
    return;
  }

  if (agentID) {
    storage.setItem(makeLastSelectedAgentStorageKey(taskID), agentID);
  } else {
    storage.removeItem(makeLastSelectedAgentStorageKey(taskID));
  }
}

export function TaskView() {
  const agents = useAgentexTaskAgents();
  const [defaultValues, setDefaultValues] =
    useState<CreateUserMessageDefaultValues | null>(null);
  const task = useAgentexTask();
  const messages = useAgentexTaskStore((s) => s.messages);
  const streamStatus = useAgentexTaskStore((s) => s.streamStatus);

  const { isSendMessageEnabled, sendMessage } = useAgentexTaskController();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);

  // get default agent ID from storage
  useEffect(() => {
    if (task === undefined) {
      return;
    }

    const lastSelectedAgentID = getStorage()?.getItem(
      makeLastSelectedAgentStorageKey(task.id)
    );
    setDefaultValues({
      textContent: null,
      agentID: lastSelectedAgentID,
    });
  }, [task?.id ?? "", setDefaultValues]);

  const isTaskTerminal = task?.status != null && task.status !== "RUNNING";
  const showForm =
    !isTaskTerminal && defaultValues !== null && isSendMessageEnabled;
  const showFormLoading = !isTaskTerminal && !showForm;

  const theme = useSafeTheme();

  return (
    <div className="flex flex-col gap-4">
      <AgentexTaskInfo />

      <MemoizedTaskMessagesComponent messages={messages} theme={theme} />

      <div className="text-destructive min-h-8" role="alert" aria-live="polite">
        {streamStatus === "reconnecting"
          ? "Reconnecting..."
          : streamStatus === "error"
          ? "Failed to connect to task"
          : errorMessage}
      </div>

      {showForm && (
        <CreateUserMessageForm
          agentOptions={agents}
          defaultValues={defaultValues}
          disabled={isSending}
          theme={theme}
          onSubmit={(data, resetForm) => {
            if (task === undefined) {
              setErrorMessage("Task not found");
              return;
            }

            setErrorMessage(null);
            const storage = getStorage();
            if (storage !== null) {
              saveLastSelectedAgent(task.id, data.agentID, storage);
            }

            setIsSending(true);
            sendMessage(
              data.agentID,
              data.kind === "data"
                ? {
                    author: "user",
                    type: "data",
                    data: data.content,
                  }
                : {
                    author: "user",
                    type: "text",
                    format: "markdown",
                    content: data.content,
                  }
            ).then(
              () => {
                setIsSending(false);
                setDefaultValues({
                  agentID: data.agentID,
                  textContent: null,
                });
                resetForm({
                  agentID: data.agentID,
                  textContent: "",
                  dataContent: "",
                  kind: data.kind,
                });
              },
              (error) => {
                console.error(error);

                const caughtErrorMessage: string | null =
                  typeof error === "object" &&
                  error !== null &&
                  "message" in error &&
                  typeof error.message === "string"
                    ? error.message
                    : null;

                setErrorMessage(
                  caughtErrorMessage ?? "Failed to send message."
                );
                setDefaultValues({
                  agentID: data.agentID,
                });
              }
            );
          }}
        >
          <CreateUserMessageFormContent />
          <CreateUserMessageFormSelectedAgent
            render={({ agent }) => <AgentInfo agent={agent} />}
          />
        </CreateUserMessageForm>
      )}
      {showFormLoading && <Skeleton className="w-full h-61 animate-pulse" />}
      {task?.status && (
        <div className="flex items-center gap-2 h-61">
          <TaskStatusIcon status={task.status} />
          Task status: {task.status}
        </div>
      )}
    </div>
  );
}
