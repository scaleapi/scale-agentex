import { JsonViewer } from '@/components/agentex/json-viewer';
import { ResizableSidebar } from '@/components/agentex/resizable-sidebar';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useSpans } from '@/hooks/use-spans';

const MIN_SIDEBAR_WIDTH = 350;
const DEFAULT_SIDEBAR_WIDTH = 350;

export type TracesSidebarProps = {
  isOpen: boolean;
  taskId: string | null;
};

export function TracesSidebar({ isOpen, taskId }: TracesSidebarProps) {
  const { spans, isLoading, error } = useSpans(taskId);

  return (
    <ResizableSidebar
      side="right"
      storageKey="tracesSidebarWidth"
      defaultWidth={DEFAULT_SIDEBAR_WIDTH}
      minWidth={MIN_SIDEBAR_WIDTH}
      isCollapsed={!isOpen}
      collapsedWidth={0}
    >
      <TooltipProvider>
        <div className="flex h-full flex-col">
          <div className="border-sidebar-border border-b px-4 py-4">
            <h2 className="text-sidebar-foreground text-lg font-semibold">
              Traces
            </h2>
            <p className="text-muted-foreground mt-1 text-sm">
              Span details and execution data
            </p>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {!taskId && (
              <div className="text-muted-foreground text-sm">
                Select a task to view traces
              </div>
            )}

            {isLoading && (
              <div className="text-muted-foreground text-sm">
                Loading traces...
              </div>
            )}

            {error && (
              <div className="text-destructive text-sm">Error: {error}</div>
            )}

            {spans.length === 0 && !isLoading && !error && taskId && (
              <div className="text-muted-foreground text-sm">
                No spans found for this task
              </div>
            )}

            {spans.map(span => {
              const startTime = new Date(span.start_time);

              return (
                <div key={span.id}>
                  <div className="mb-2 flex items-baseline gap-2">
                    <h3 className="text-sidebar-foreground text-sm font-medium">
                      {span.name}
                    </h3>
                    <Tooltip delayDuration={0}>
                      <TooltipTrigger asChild>
                        <span className="text-muted-foreground text-xs">
                          {startTime.toLocaleTimeString()}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>
                        {startTime.toLocaleString()}
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <JsonViewer
                    data={JSON.parse(JSON.stringify(span))}
                    defaultExpanded={false}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </TooltipProvider>
    </ResizableSidebar>
  );
}
