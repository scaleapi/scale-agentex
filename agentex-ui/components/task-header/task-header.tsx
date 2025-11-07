import { motion } from 'framer-motion';
import { Activity, Bot } from 'lucide-react';

import { InvestigateTracesButton } from '@/components/task-header/investigate-traces-button';
import { ThemeToggle } from '@/components/task-header/theme-toggle';
import { CopyButton } from '@/components/ui/copy-button';
import { IconButton } from '@/components/ui/icon-button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';

import type { Agent } from 'agentex/resources';

type TaskHeaderProps = {
  taskId: string | null;
  isTracesSidebarOpen?: boolean;
  toggleTracesSidebar?: () => void;
  agents?: Agent[];
  selectedAgentName?: string;
  onAgentChange?: (agentName: string | undefined) => void;
  ref?: React.RefObject<HTMLDivElement | null>;
};

export function TaskHeader({
  taskId,
  isTracesSidebarOpen,
  toggleTracesSidebar,
  agents = [],
  onAgentChange,
  ref,
}: TaskHeaderProps) {
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
    <motion.div
      ref={ref}
      className="sticky top-0 h-16 w-full"
      key="topbar"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
    >
      <BlurredGradientBackground />
      <div className="relative flex h-full w-full items-center justify-between px-4">
        <div
          className={`flex items-center gap-2 ${!taskId && 'pointer-events-none invisible'}`}
        >
          <span className="text-muted-foreground text-sm">Task ID:</span>
          <span className="text-foreground text-sm">{displayTaskId}</span>
          <CopyButton tooltip="Copy full ID" onClick={copyTaskId} />
        </div>

        <div className="bg-background flex items-center gap-2 rounded-full shadow-sm">
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

        <div
          className={`flex items-center gap-2 ${!taskId && 'pointer-events-none invisible'}`}
        >
          <ThemeToggle />
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
          {taskId && <InvestigateTracesButton taskId={taskId} />}
        </div>
      </div>
    </motion.div>
  );
}

function BlurredGradientBackground() {
  return (
    <div
      className="from-background/80 absolute inset-0 bg-gradient-to-b to-transparent backdrop-blur-xs"
      style={{
        maskImage:
          'linear-gradient(to bottom, black 0%, black 50%, transparent 100%)',
        WebkitMaskImage:
          'linear-gradient(to bottom, black 0%, black 50%, transparent 100%)',
      }}
    />
  );
}
