import { AgentexTask } from "@/registry/agentex/agentex-task/components/agentex-task";
import { toast } from "react-toastify";
import { CreateTaskView } from "./create-task-view";
import { Loading } from "./loading";
import { TaskView } from "./task-view";

type Props = {
  selectedTaskID: string | null;
  setSelectedTask: (taskID: string | null) => void;
};

export function MainContentViewController({
  selectedTaskID,
  setSelectedTask,
}: Props) {
  if (selectedTaskID === null) {
    return <CreateTaskView onTaskCreated={setSelectedTask} />;
  }

  return (
    <AgentexTask
      taskID={selectedTaskID}
      fallback={<Loading />}
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
          `Failed to load task: ID=${selectedTaskID} ${
            caughtErrorMessage ?? "unknown error"
          }`
        );
      }}
    >
      <TaskView />
    </AgentexTask>
  );
}
