import { Activity, Bot } from 'lucide-react';

import { CopyButton } from '@/components/agentex/copy-button';
import { IconButton } from '@/components/agentex/icon-button';
import { InvestigateTracesButton } from '@/components/agentex/investigate-traces-button';
import { ThemeToggle } from '@/components/agentex/theme-toggle';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';

import type { Agent } from 'agentex/resources';

type TaskTopBarProps = {
  taskId: string | null;
  isTracesSidebarOpen?: boolean;
  toggleTracesSidebar?: () => void;
  agents?: Agent[];
  selectedAgentName?: string;
  onAgentChange?: (agentName: string | undefined) => void;
};

export function TaskTopBar({
  taskId,
  isTracesSidebarOpen,
  toggleTracesSidebar,
  agents = [],
  onAgentChange,
}: TaskTopBarProps) {
  const displayTaskId = taskId ? taskId.split('-')[0] : '';
  const { agentName: selectedAgentName } = useSafeSearchParams();

  const copyTaskId = async () => {
    if (taskId) {
      try {
        await navigator.clipboard.writeText(taskId);
      } catch (err) {
        console.error('Failed to copy task ID:', err);
      }
    }
  };

  return (
    <div className="bg-background sticky top-0 z-10 h-16 w-full">
      <div className="relative flex h-full items-center justify-between px-4">
        <div className="flex items-center gap-2">
          {taskId && (
            <>
              <span className="text-muted-foreground text-sm">Task ID:</span>
              <span className="text-foreground text-sm">{displayTaskId}</span>
              {taskId && (
                <CopyButton tooltip="Copy full ID" onClick={copyTaskId} />
              )}
            </>
          )}
        </div>
        <div className="absolute left-1/2 flex -translate-x-1/2 items-center gap-2">
          {agents.length > 0 && onAgentChange && (
            <Select
              value={selectedAgentName ?? ''}
              onValueChange={value => {
                onAgentChange(value === selectedAgentName ? undefined : value);
              }}
            >
              <SelectTrigger className="max-w-60" aria-label="Select Agent">
                <Bot />
                <SelectValue placeholder="Select Agent" />
              </SelectTrigger>
              <SelectContent>
                {agents.map(agent => (
                  <SelectItem key={agent.name} value={agent.name}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {taskId && (
            <>
              {toggleTracesSidebar && (
                <IconButton
                  variant="ghost"
                  onClick={toggleTracesSidebar}
                  aria-label={
                    isTracesSidebarOpen
                      ? 'Close traces sidebar'
                      : 'Open traces sidebar'
                  }
                  icon={Activity}
                />
              )}
              <InvestigateTracesButton taskId={taskId} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
