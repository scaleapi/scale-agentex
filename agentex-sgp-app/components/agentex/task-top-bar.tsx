import { CopyButton } from '@/components/agentex/copy-button';
import { ThemeToggle } from '@/components/agentex/theme-toggle';
import { InvestigateTracesButton } from '@/components/agentex/investigate-traces-button';

export function TaskTopBar({ taskId }: { taskId: string | null }) {
  const displayTaskId = taskId ? taskId.split('-')[0] : '';

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
    <div className="sticky top-0 bg-background z-10 flex items-center justify-between h-16 px-4">
      <div className="flex items-center gap-2">
        {taskId && (
          <>
            <span className="text-sm" style={{ color: '#6B7280' }}>
              Task ID:
            </span>
            <span className="text-foreground text-sm">{displayTaskId}</span>
            {taskId && (
              <CopyButton tooltip="Copy full ID" onClick={copyTaskId} />
            )}
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        {taskId && <InvestigateTracesButton taskId={taskId} />}
      </div>
    </div>
  );
}
