import { Skeleton } from "@/components/ui/skeleton";
import { AgentexTask } from "@/registry/agentex/agentex-task/components/agentex-task";
import { CreateTaskView } from "@/registry/agentex/quickstart/create-task-view";
import { useSafeSearchParams } from "@/registry/agentex/quickstart/hooks/use-safe-search-params";
import { TaskView } from "@/registry/agentex/quickstart/task-view";
import { toast } from "react-toastify";

/**
 * This controls which view gets shown
 * 1. CreateTaskView
 * 2. TaskView
 */
export function MainViewController() {
  const { taskID } = useSafeSearchParams();

  if (taskID === null) {
    return <CreateTaskView />;
  }

  return (
    <AgentexTask
      taskID={taskID}
      fallback={<Skeleton className="w-full h-96" />}
      onError={(error) => {
        console.error(error);

        const caughtErrorMessage: string | null =
          typeof error === "object" &&
          error !== null &&
          "message" in error &&
          typeof error.message === "string"
            ? error.message
            : null;

        toast.error(
          `Failed to load task: ID=${taskID} ${
            caughtErrorMessage ?? "unknown error"
          }`
        );
      }}
    >
      <TaskView />
    </AgentexTask>
  );
}
