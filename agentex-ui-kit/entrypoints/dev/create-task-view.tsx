import { AgentInfo } from "@/components/agent-info";
import { Textarea } from "@/components/ui/textarea";
import { useSafeTheme } from "@/hooks/use-safe-theme";
import { useAgentexRootController } from "@/registry/agentex/agentex-root/hooks/use-agentex-root-controller";
import { useAgentexRootStore } from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import {
  CreateUserMessageForm,
  CreateUserMessageFormContent,
  CreateUserMessageFormSelectedAgent,
} from "@/registry/agentex/create-user-message-form/create-user-message-form";
import type { Task } from "agentex/resources";
import { useState } from "react";
import z from "zod";

const taskParamsSchema = z
  .string()
  .max(100_000)
  .transform((arg, ctx): null | Record<string, unknown> => {
    if (!arg) {
      return null;
    }
    try {
      const jsonValue = JSON.parse(arg);
      const recordParseResult = z
        .record(z.string(), z.unknown())
        .safeParse(jsonValue);
      if (recordParseResult.success) {
        return recordParseResult.data;
      }

      for (const issue of recordParseResult.error.issues) {
        ctx.addIssue(issue);
      }
    } catch {
      ctx.addIssue({
        code: "custom",
        message: "Task params must be a valid JSON object",
      });
    }
    return z.NEVER;
  });

type Props = {
  onTaskCreated: (taskID: Task["id"]) => void;
};

export function CreateTaskView({ onTaskCreated }: Props) {
  const agents = useAgentexRootStore((s) => s.agents);
  const { createTask } = useAgentexRootController();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [formDisabled, setFormDisabled] = useState(false);
  const [taskParams, setTaskParams] = useState<string>("");

  const theme = useSafeTheme();

  return (
    <div className="flex flex-col gap-4">
      <div className="text-destructive min-h-8" role="alert" aria-live="polite">
        {errorMessage}
      </div>
      <CreateUserMessageForm
        agentOptions={agents}
        disabled={formDisabled}
        theme={theme}
        onSubmit={(data, resetForm) => {
          const taskParamsParseResult = taskParamsSchema.safeParse(taskParams);

          if (!taskParamsParseResult.success) {
            setErrorMessage(
              "Invalid task params: " + taskParamsParseResult.error.message
            );
            return;
          }

          setErrorMessage(null);
          setFormDisabled(true);
          createTask(
            data.agentID,
            null, // TODO: task name? this needs to be a unique ID
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
                },
            taskParamsParseResult.data
          ).then(
            (task) => {
              setFormDisabled(false);
              resetForm();
              onTaskCreated(task.id);
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
        <div>
          <label htmlFor="create-task-form-task-params">Task Params</label>
          <Textarea
            id="create-task-form-task-params"
            value={taskParams}
            onChange={(e) => setTaskParams(e.target.value)}
          />
        </div>
        <CreateUserMessageFormContent />
        <CreateUserMessageFormSelectedAgent
          render={({ agent }) => <AgentInfo agent={agent} />}
        />
      </CreateUserMessageForm>
    </div>
  );
}
