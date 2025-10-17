import { useAgentexSingleAgentRootController } from "@/registry/agentex/agentex-single-agent-root/hooks/use-agentex-single-agent-root-controller";
import { useSingleAgent } from "@/registry/agentex/agentex-single-agent-root/hooks/use-single-agent";
import {
  CreateUserMessageForm,
  CreateUserMessageFormContent,
} from "@/registry/agentex/create-user-message-form/create-user-message-form";
import { useSafeSearchParams } from "@/registry/agentex/quickstart/hooks/use-safe-search-params";
import { useState } from "react";

/**
 * This is the UI that appears when no task is selected.
 */
export function CreateTaskView() {
  // state + controllers from root context (see agent-app.tsx)
  const agent = useSingleAgent();
  const { createTask } = useAgentexSingleAgentRootController();

  // search params (used to switch to the task the user creates)
  const { setTaskID } = useSafeSearchParams();

  // local state
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [formDisabled, setFormDisabled] = useState(false);

  // TODO: this depends on your app
  const theme = "light";

  return (
    <div className="flex flex-col gap-4">
      <div className="text-destructive min-h-8" role="alert" aria-live="polite">
        {errorMessage}
      </div>

      <CreateUserMessageForm
        agentOptions={[agent]}
        disabled={formDisabled}
        theme={theme}
        onSubmit={(data, resetForm) => {
          setErrorMessage(null);
          setFormDisabled(true);
          createTask(
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
            (task) => {
              setFormDisabled(false);
              resetForm();
              setTaskID(task.id);
            },
            (error) => {
              setFormDisabled(false);
              console.error(error);

              const caughtErrorMessage: string | null =
                typeof error === "object" &&
                error !== null &&
                "message" in error &&
                typeof error.message === "string"
                  ? error.message
                  : null;

              setErrorMessage(caughtErrorMessage ?? "Failed to send message.");
            }
          );
        }}
      >
        <CreateUserMessageFormContent />
      </CreateUserMessageForm>
    </div>
  );
}
