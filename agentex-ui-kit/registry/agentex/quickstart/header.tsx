import { Button } from "@/components/ui/button";
import { useAgentexRootStore } from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import { useSingleAgent } from "@/registry/agentex/agentex-single-agent-root/hooks/use-single-agent";
import { AllTasksSheet } from "@/registry/agentex/all-tasks-sheet/all-tasks-sheet";
import { ExpandablePre } from "@/registry/agentex/expandable-pre/expandable-pre";
import { useSafeSearchParams } from "@/registry/agentex/quickstart/hooks/use-safe-search-params";
import type { Agent } from "agentex/resources";
import { Suspense } from "react";

type ImplProps = {
  agent: Agent;
};

/**
 * A simple header that looks like this:
 *                     Agent Name
 * Status    Description        New Task    View All Tasks
 */
function HeaderImpl({ agent }: ImplProps) {
  // state from agentex root context (see agent-app.tsx)
  const tasks = useAgentexRootStore((state) => state.tasks);

  const { taskID, setTaskID } = useSafeSearchParams();

  return (
    <header className="w-full mt-4">
      <div className="mx-auto max-w-[min(100%-var(--spacing)*4,var(--spacing)*256)]">
        <div className="flex flex-col justify-center gap-2 my-2 mx-4">
          <button
            className="hover:underline hover:text-accent-foreground"
            onClick={() => setTaskID(null)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setTaskID(null);
              }
            }}
          >
            <h1>{agent.name}</h1>
          </button>

          <div className="flex justify-between items-end-safe">
            <div className="flex items-baseline gap-2 p-1">
              Status: {agent.status} {agent.status_reason}
              <div className="h-7 overflow-visible mr-2 bg-background p-1 rounded-md z-1">
                <ExpandablePre lineClampValue={1}>
                  {agent.description}
                </ExpandablePre>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-1">
              {taskID !== null && (
                <Button
                  className="h-10"
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setTaskID(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setTaskID(null);
                    }
                  }}
                >
                  New task
                </Button>
              )}

              <AllTasksSheet
                tasks={tasks}
                selectedTaskID={taskID}
                onSelectTask={setTaskID}
              />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

export function Header() {
  const agent = useSingleAgent();

  return (
    <Suspense
      fallback={
        <header className="w-full mt-4">
          <div className="mx-auto max-w-[min(100%-var(--spacing)*4,var(--spacing)*256)]">
            <div className="flex flex-col justify-center gap-2 my-2 mx-4">
              <h1>{agent.name}</h1>

              <div className="flex justify-start items-end-safe">
                <div className="flex items-baseline gap-2 p-1">
                  Status: {agent.status} {agent.status_reason}
                  <div className="h-7 overflow-visible mr-2">
                    <ExpandablePre
                      lineClampValue={1}
                      className="bg-background p-1 rounded-md"
                    >
                      {agent.description}
                    </ExpandablePre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </header>
      }
    >
      <HeaderImpl agent={agent} />
    </Suspense>
  );
}
