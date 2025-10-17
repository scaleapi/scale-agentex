import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useSingleAgentTaskController } from "@/registry/agentex/agentex-single-agent-root/hooks/use-agentex-single-agent-task-controller";
import { useSingleAgent } from "@/registry/agentex/agentex-single-agent-root/hooks/use-single-agent";
import {
  useAgentexTask,
  useAgentexTaskStore,
} from "@/registry/agentex/agentex-task/hooks/use-agentex-task-store";
import {
  CreateUserMessageForm,
  CreateUserMessageFormContent,
} from "@/registry/agentex/create-user-message-form/create-user-message-form";
import { TaskMessagesComponent } from "@/registry/agentex/task-messages/task-messages";
import { useState } from "react";

/**
 * This is the UI that appears when a task is selected.
 */
export function TaskView() {
  // state + controllers from root context (see agent-app.tsx)
  const agent = useSingleAgent();
  const { isSendMessageEnabled, sendMessage } = useSingleAgentTaskController();

  // state from task context (see main-view-controller.tsx)
  const task = useAgentexTask();
  const messages = useAgentexTaskStore((s) => s.messages);
  const streamStatus = useAgentexTaskStore((s) => s.streamStatus);

  // local state
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);

  // computed view
  const isTaskTerminal = task?.status != null && task.status !== "RUNNING";
  const showForm = !isTaskTerminal && isSendMessageEnabled;
  const showFormLoading = !isTaskTerminal && !showForm;

  // TODO: this depends on your app
  const theme = "light";

  return (
    <div className="flex flex-col gap-4">
      <TaskMessagesComponent messages={messages} theme={theme} />
      <div className="text-destructive min-h-8" role="alert" aria-live="polite">
        {streamStatus === "reconnecting"
          ? "Reconnecting..."
          : streamStatus === "error"
          ? "Failed to connect to task"
          : errorMessage}
      </div>

      {showForm && (
        <CreateUserMessageForm
          agentOptions={[agent]}
          disabled={isSending}
          theme={theme}
          onSubmit={(data, resetForm) => {
            setErrorMessage(null);
            setIsSending(true);
            sendMessage(
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
                resetForm();
              },
              (error) => {
                setIsSending(false);
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
              }
            );
          }}
        >
          <CreateUserMessageFormContent />
        </CreateUserMessageForm>
      )}
      {showFormLoading && <Skeleton className="w-full h-61 animate-pulse" />}
      <div
        className={cn("mx-auto", {
          invisible: !isTaskTerminal,
        })}
      >
        Task status: {task?.status} {task?.status_reason}
      </div>
    </div>
  );
}
