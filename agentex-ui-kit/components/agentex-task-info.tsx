import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useAgentexTask } from "@/registry/agentex/agentex-task/hooks/use-agentex-task-store";
import { TaskStatusIcon } from "@/registry/agentex/task-status-icon/task-status-icon";
import { ChevronsUpDown } from "lucide-react";

export type AgentexTaskInfoProps = {
  fallback?: React.ReactNode;
};

/**
 * WIP
 */
export function AgentexTaskInfo({ fallback }: AgentexTaskInfoProps) {
  const task = useAgentexTask();

  if (task === undefined) {
    return <>{fallback}</>;
  }

  return (
    <Collapsible className="flex flex-col gap-2">
      <div className="flex items-baseline-last">
        <h2>{task.name ?? "Unnamed Task"}</h2>
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="icon" className="size-8 m-2">
            <ChevronsUpDown />
            <span className="sr-only">Details</span>
          </Button>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent className="flex flex-col gap-2">
        <div className="rounded-md border px-4 py-2 font-mono text-sm">
          ID: {task.id}
        </div>

        {task.status != null && (
          <div className="rounded-md border px-4 py-2 font-mono text-sm flex items-center gap-2">
            <TaskStatusIcon status={task.status} />
            <span>
              {task.status}: {task.status_reason ?? "<no reason>"}
            </span>
          </div>
        )}

        {task.created_at != null && (
          <div className="rounded-md border px-4 py-2 font-mono text-sm">
            Created at: {task.created_at}
          </div>
        )}

        {task.updated_at != null && (
          <div className="rounded-md border px-4 py-2 font-mono text-sm">
            Updated at: {task.updated_at}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
