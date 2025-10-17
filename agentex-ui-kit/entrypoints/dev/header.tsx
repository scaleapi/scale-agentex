import { AllTasksSheet } from "@/registry/agentex/all-tasks-sheet/all-tasks-sheet";
import { Button } from "@/components/ui/button";
import { AgentexDevClientSetupFormTrigger } from "@/registry/agentex/agentex-dev-root/components/agentex-dev-client-setup-form";
import { useAgentexRootStore } from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import { memo } from "react";

type Props = {
  onSelectTask: (taskID: string | null) => void;
  selectedTaskID: string | null;
};

function HeaderImpl({ onSelectTask, selectedTaskID }: Props) {
  const tasks = useAgentexRootStore((s) => s.tasks);
  return (
    <header className="w-full sm:sticky mt-4 sm:top-0 sm:z-10 bg-background">
      <div className="mx-auto max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width))]">
        <div className="my-2 flex flex-col items-center-safe gap-2 sm:flex-row sm:items-baseline-last sm:justify-between">
          <button
            onClick={() => onSelectTask(null)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectTask(null);
              }
            }}
          >
            <h1>Agentex UI</h1>
          </button>
          <div className="flex items-baseline-last justify-center-safe sm:justify-end-safe gap-2">
            <AgentexDevClientSetupFormTrigger asChild>
              <Button variant="outline">Client Setup</Button>
            </AgentexDevClientSetupFormTrigger>
            <AllTasksSheet
              tasks={tasks}
              selectedTaskID={selectedTaskID}
              onSelectTask={onSelectTask}
            />
          </div>
        </div>
      </div>
    </header>
  );
}

export const Header = memo(HeaderImpl);
