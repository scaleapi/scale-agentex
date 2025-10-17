'use client';

import {Badge} from '@/components/ui/badge';
import {Card, CardContent} from '@/components/ui/card';
import {cn} from '@/lib/utils';
import {X} from 'lucide-react';
import type {Span as TraceSpan} from './GanttChart';

interface TraceDetailSidebarProps {
  open: boolean;
  selectedTrace: TraceSpan | null;
  onClose: () => void;
}

export function TraceDetailSidebar({
  open,
  selectedTrace,
  onClose,
}: TraceDetailSidebarProps) {
  // Format time difference as ms, μs, or ns
  const formatDuration = (ms: number) => {
    if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
    if (ms >= 1) return `${ms.toFixed(2)}ms`;
    if (ms >= 0.001) return `${(ms * 1000).toFixed(2)}μs`;
    return `${(ms * 1000000).toFixed(2)}ns`;
  };

  // Format absolute time
  const formatTime = (timestamp: Date) => {
    return `${timestamp.toLocaleTimeString()}.${timestamp
      .getMilliseconds()
      .toString()
      .padStart(3, '0')}`;
  };

  // Calculate duration between start and end times
  const calculateDuration = (span: TraceSpan): number => {
    const startTime =
      span.start_time instanceof Date ? span.start_time : new Date(span.start_time);
    const endTime = span.end_time
      ? span.end_time instanceof Date
        ? span.end_time
        : new Date(span.end_time)
      : new Date(); // If no end time, use current time

    return endTime.getTime() - startTime.getTime();
  };

  return (
    <div
      className={cn(
        'fixed inset-y-0 right-0 z-50 w-[400px] transform overflow-auto border-l bg-background shadow-lg transition-transform duration-300 ease-in-out sm:w-[540px]',
        open ? 'translate-x-0' : 'translate-x-full'
      )}
    >
      <div className="flex items-center justify-between border-b p-4">
        <h2 className="text-lg font-semibold">{selectedTrace?.name}</h2>
        <button onClick={onClose} className="rounded-full p-1 hover:bg-muted">
          <X className="h-5 w-5" />
          <span className="sr-only">Close</span>
        </button>
      </div>

      {selectedTrace && (
        <div className="p-6">
          <div className="grid grid-cols-2 gap-4 py-4">
            <div>
              <p className="mb-1 text-sm font-medium">Type</p>
              <Badge>{selectedTrace.type || 'default'}</Badge>
            </div>
            <div>
              <p className="mb-1 text-sm font-medium">Duration</p>
              <p>{formatDuration(calculateDuration(selectedTrace))}</p>
            </div>
            <div>
              <p className="mb-1 text-sm font-medium">Start Time</p>
              <p>
                {formatTime(
                  selectedTrace.start_time instanceof Date
                    ? selectedTrace.start_time
                    : new Date(selectedTrace.start_time)
                )}
              </p>
            </div>
            <div>
              <p className="mb-1 text-sm font-medium">End Time</p>
              <p>
                {selectedTrace.end_time
                  ? formatTime(
                      selectedTrace.end_time instanceof Date
                        ? selectedTrace.end_time
                        : new Date(selectedTrace.end_time)
                    )
                  : 'Ongoing'}
              </p>
            </div>
          </div>

          <Card>
            <CardContent className="p-4">
              <p className="mb-2 text-sm font-medium">Trace Data</p>
              <pre className="max-h-[300px] overflow-auto rounded-md bg-muted p-4 text-xs">
                {JSON.stringify(selectedTrace.data || {}, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
