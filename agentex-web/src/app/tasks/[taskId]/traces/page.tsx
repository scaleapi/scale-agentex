'use client';

import {GanttChart, type Span} from '@/components/tracing/GanttChart';
import {Alert, AlertDescription} from '@/components/ui/alert';
import {Button} from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {Label} from '@/components/ui/label';
import {Switch} from '@/components/ui/switch';
import {Tabs, TabsContent, TabsList, TabsTrigger} from '@/components/ui/tabs';
import {useToast} from '@/hooks/use-toast';
import AgentexSDK from 'agentex';
import {AlertCircle, ArrowLeft, Download, X} from 'lucide-react';
import Link from 'next/link';
import {useParams} from 'next/navigation';
import {useCallback, useEffect, useRef, useState} from 'react';

const BASE_URL = process.env.AGENTEX_BASE_URL || 'http://localhost:5003';

const client = new AgentexSDK({baseURL: BASE_URL, apiKey: 'dummy'});

// Empty data for initial state
const emptyData: Span[] = [];

// Add this component at the top level, outside the main component
// This ensures the animation stays consistent and doesn't cause re-renders
function PulsingIndicator() {
  return (
    <span
      className="ml-1.5 h-2 w-2 rounded-full bg-green-500"
      style={{
        animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }}
    />
  );
}

export default function TraceViewer() {
  const {taskId} = useParams();
  const {toast} = useToast();
  const [error, setError] = useState<string | null>(null);
  const [spans, setSpans] = useState<Span[]>(emptyData);
  const [selectedSpan, setSelectedSpan] = useState<Span | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [isManualLoading, setIsManualLoading] = useState(false);

  // Polling control refs
  const pollingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isPollingLockedRef = useRef<boolean>(false);
  const lastPollTimeRef = useRef<number>(0);
  const previousSpanCountRef = useRef<number>(0);
  const selectedSpanIdRef = useRef<string | null>(null);

  // Polling configuration
  const STRICT_POLL_INTERVAL = 2000; // Exactly 2 seconds
  const MIN_POLL_INTERVAL = 1900; // Absolute minimum time between refreshes

  // Function to handle toggling polling state - the only place that should toggle polling
  const togglePolling = useCallback(() => {
    // If turning off polling, immediately clear any pending timeouts
    if (isPolling) {
      if (pollingTimeoutRef.current) {
        clearTimeout(pollingTimeoutRef.current);
        pollingTimeoutRef.current = null;
      }
    }
    setIsPolling(prev => !prev);
  }, [isPolling]);

  // Update selectedSpanIdRef whenever selectedSpan changes
  useEffect(() => {
    selectedSpanIdRef.current = selectedSpan?.id || null;
  }, [selectedSpan]);

  // Main function to load trace data
  const loadTraceData = useCallback(
    async (isManualRefresh = false) => {
      if (!taskId || typeof taskId !== 'string') {
        return;
      }

      // GUARD: Check if polling is locked (another request is in progress)
      if (isPollingLockedRef.current) {
        console.log('[STRICT] Skipping poll - already polling');
        return;
      }

      // GUARD: Enforce strict time interval between polls
      const now = Date.now();
      const timeSinceLastPoll = now - lastPollTimeRef.current;

      if (!isManualRefresh && timeSinceLastPoll < MIN_POLL_INTERVAL) {
        console.log(
          `[STRICT] Poll too soon (${timeSinceLastPoll}ms since last poll). Enforcing rate limit.`
        );
        return;
      }

      // LOCK: Set the polling lock and update time
      isPollingLockedRef.current = true;
      lastPollTimeRef.current = now;

      // Set loading states appropriately
      if (isManualRefresh) {
        setIsManualLoading(true);
      }
      setError(null);

      try {
        // Fetch the spans using traceId
        const spans = await client.spans.list(
          {
            trace_id: taskId,
          },
          {
            fetchOptions: {cache: 'no-store'},
          }
        );

        // Keep track of previous span count to detect changes
        const currentSpanCount = spans.length;
        const previousSpanCount = previousSpanCountRef.current;

        // Get current selected span ID from ref to avoid dependency issues
        const currentSelectedSpanId = selectedSpanIdRef.current;

        setSpans(spans);
        // Update the previous span count ref
        previousSpanCountRef.current = currentSpanCount;

        // If there was a selected span, try to find and reselect it in the new data
        if (currentSelectedSpanId) {
          const updatedSelectedSpan = spans.find(
            span => span.id === currentSelectedSpanId
          );
          if (updatedSelectedSpan) {
            // During auto-refresh polls, don't update the selectedSpan state to prevent re-renders
            if (isManualRefresh || !isPolling) {
              setSelectedSpan(updatedSelectedSpan);
            }
          }
        }

        // When auto-refreshing, only show a toast if the span count has changed
        if (isPolling && !isManualRefresh) {
          if (currentSpanCount !== previousSpanCount) {
            toast({
              title: 'New Spans Detected',
              description: `Updated from ${previousSpanCount} to ${currentSpanCount} spans`,
              duration: 2000,
            });
          }
        } else {
          // Always show a toast for manual refresh
          toast({
            title: 'Trace Data Loaded',
            description: `Successfully loaded ${currentSpanCount} spans`,
          });
        }
      } catch (err) {
        console.error('Error loading trace data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load trace data');
        toast({
          variant: 'destructive',
          title: 'Error Loading Traces',
          description: err instanceof Error ? err.message : 'Failed to load trace data',
        });

        // Set empty data on error
        setSpans(emptyData);
        previousSpanCountRef.current = 0;
      } finally {
        // Only update loading states if this is not an auto-refresh or we're doing a manual refresh
        if (isManualRefresh) {
          setIsManualLoading(false);
        }

        // Release the polling lock
        isPollingLockedRef.current = false;
      }
    },
    // Remove selectedSpan from dependencies - we use the ref instead
    [taskId, toast, isPolling]
  );

  // Load trace data on initial render
  useEffect(() => {
    loadTraceData(true);
  }, [taskId, loadTraceData]);

  // Single, controlled polling effect
  useEffect(() => {
    let isActive = true; // Closure variable to prevent stale callbacks

    // Setup function for polling
    const setupPolling = () => {
      // Clear any existing timeout first
      if (pollingTimeoutRef.current) {
        clearTimeout(pollingTimeoutRef.current);
        pollingTimeoutRef.current = null;
      }

      // If not polling, don't set up a new timer
      if (!isPolling || !isActive) return;

      // Single poll function that also schedules the next poll
      const poll = () => {
        // Safety checks - only proceed if polling is still enabled and component is mounted
        if (!isPolling || !isActive) {
          console.log('[STRICT] Polling stopped or component unmounted');
          return;
        }

        // Additional safety check for rapid consecutive calls
        const now = Date.now();
        const timeSinceLastPoll = now - lastPollTimeRef.current;
        if (timeSinceLastPoll < MIN_POLL_INTERVAL) {
          console.log(
            `[STRICT-POLL] Too soon to poll (${timeSinceLastPoll}ms). Rescheduling.`
          );
          // Reschedule after the minimum interval has passed
          pollingTimeoutRef.current = setTimeout(
            poll,
            MIN_POLL_INTERVAL - timeSinceLastPoll + 100
          );
          return;
        }

        console.log('[STRICT] Executing controlled poll');

        // Execute the data load - only if we're not already loading
        if (!isPollingLockedRef.current) {
          loadTraceData(false).finally(() => {
            // After loading completes (success or failure), schedule next poll
            // but only if we're still in polling mode and component is mounted
            if (isPolling && isActive) {
              console.log('[STRICT] Scheduling next poll in exactly 2 seconds');
              pollingTimeoutRef.current = setTimeout(poll, STRICT_POLL_INTERVAL);
            }
          });
        } else {
          // If already loading, reschedule after a delay
          console.log('[STRICT] Previous poll still running, rescheduling');
          pollingTimeoutRef.current = setTimeout(poll, 1000);
        }
      };

      // Start the first poll with a small delay to let things settle
      console.log('[STRICT] Starting initial poll');
      pollingTimeoutRef.current = setTimeout(poll, 500);
    };

    // Handle polling state changes
    if (isPolling) {
      // Notify user that polling has started
      toast({
        title: 'Auto-refresh enabled',
        description: 'Trace data will update every 2 seconds',
        duration: 3000,
      });

      // Start polling
      setupPolling();
    } else {
      // Notify user that polling has stopped
      if (pollingTimeoutRef.current) {
        toast({
          title: 'Auto-refresh disabled',
          description: 'Automatic updates have been stopped',
          duration: 3000,
        });

        // Clean up any existing timeout
        clearTimeout(pollingTimeoutRef.current);
        pollingTimeoutRef.current = null;
      }
    }

    // Cleanup on unmount or when dependencies change
    return () => {
      isActive = false; // Mark as inactive for closure safety
      if (pollingTimeoutRef.current) {
        clearTimeout(pollingTimeoutRef.current);
        pollingTimeoutRef.current = null;
      }
    };
  }, [isPolling, loadTraceData, toast]);

  // Also clean up on component unmount
  useEffect(() => {
    return () => {
      if (pollingTimeoutRef.current) {
        clearTimeout(pollingTimeoutRef.current);
        pollingTimeoutRef.current = null;
      }
    };
  }, []);

  // Handle span selection separately from polling
  const handleSpanSelect = useCallback((span: Span) => {
    // Only change the selected span, do NOT toggle polling
    setSelectedSpan(span);
    // Update the ref immediately to avoid timing issues
    selectedSpanIdRef.current = span.id;
  }, []);

  // Format time difference as ms, μs, or ns
  function formatDuration(ms: number) {
    if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
    if (ms >= 1) return `${ms.toFixed(2)}ms`;
    if (ms >= 0.001) return `${(ms * 1000).toFixed(2)}μs`;
    return `${(ms * 1000000).toFixed(2)}ns`;
  }

  // Format absolute time
  function formatTime(timestamp: Date) {
    return `${timestamp.toLocaleTimeString()}.${timestamp
      .getMilliseconds()
      .toString()
      .padStart(3, '0')}`;
  }

  // Function to handle downloading spans as JSON
  const handleDownloadSpans = () => {
    // Create a JSON blob from the spans data
    const dataStr = JSON.stringify(spans, null, 2);
    const blob = new Blob([dataStr], {type: 'application/json'});

    // Create a download URL for the blob
    const url = URL.createObjectURL(blob);

    // Create a temporary anchor element to trigger the download
    const a = document.createElement('a');
    a.href = url;
    a.download = `trace-spans-for-task-${taskId}.json`;
    document.body.appendChild(a);
    a.click();

    // Clean up
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast({
      title: 'Download started',
      description: `Downloading ${spans.length} spans as JSON`,
      duration: 2000,
    });
  };

  return (
    <main className="container mx-auto flex h-screen flex-col px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center">
          <Link href={`/tasks/${taskId}`}>
            <Button variant="outline" size="sm" className="mr-2 flex items-center gap-1">
              <ArrowLeft className="h-4 w-4" />
              Back to Chat
            </Button>
          </Link>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Switch
              id="auto-refresh"
              checked={isPolling}
              onCheckedChange={togglePolling}
              disabled={isManualLoading}
              aria-label="Toggle auto-refresh"
            />
            <Label htmlFor="auto-refresh" className="flex cursor-pointer items-center">
              {isPolling ? (
                <span className="flex items-center">
                  Auto-refreshing
                  <PulsingIndicator />
                </span>
              ) : (
                'Auto-reload'
              )}
            </Label>
          </div>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!!(taskId && typeof taskId === 'string') && (
        <Alert className="mb-4">
          <div className="flex w-full items-center justify-between">
            <div>
              <div className="flex items-center gap-1">
                <p className="text-sm font-medium">
                  Trace ID:{' '}
                  <span className="inline-block" title={taskId}>
                    {`${taskId.substring(0, 8)}...`}
                  </span>
                </p>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(taskId || '');
                    toast({
                      title: 'Copied to clipboard',
                      description: 'Trace ID has been copied to clipboard',
                      duration: 2000,
                    });
                  }}
                  className="ml-1 rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus:outline-none"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="feather feather-copy"
                  >
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                  </svg>
                  <span className="sr-only">Copy trace ID</span>
                </button>
              </div>
              <p className="text-xs text-muted-foreground">
                Showing spans associated with this trace
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span>{spans.length} spans</span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownloadSpans}
                disabled={spans.length === 0}
                className="flex items-center gap-1"
              >
                <Download className="h-3.5 w-3.5" />
                <span className="text-xs">Download</span>
              </Button>
            </div>
          </div>
        </Alert>
      )}

      {/* Main Content Area - Gantt Chart and Detail Panel side by side */}
      <div className="mb-4 flex min-h-0 flex-1 gap-4">
        {/* Gantt Chart - Left Section */}
        <Card className="flex min-w-0 flex-1 flex-col">
          <CardHeader className="py-3">
            <CardTitle className="text-lg">Gantt Chart</CardTitle>
            <CardDescription>
              Hierarchical view of spans - click arrows to expand/collapse
            </CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-hidden p-2">
            {spans.length > 0 ? (
              <GanttChart
                spans={spans}
                onSpanSelect={handleSpanSelect} // This should only select spans, never affect polling
                selectedSpanId={selectedSpan?.id}
                autoScrollToBottom={isPolling}
              />
            ) : (
              <div className="flex h-full items-center justify-center rounded-md border">
                <p className="text-muted-foreground">No trace data available</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Span Details - Right Section (always visible with empty state when no span selected) */}
        <Card className="flex w-[450px] min-w-0 flex-col">
          {selectedSpan ? (
            <>
              <CardHeader className="flex-shrink-0 py-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="truncate text-lg" title={selectedSpan.name}>
                    {selectedSpan.name}
                  </CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSelectedSpan(null)}
                  >
                    <X className="h-4 w-4" />
                    <span className="sr-only">Close</span>
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="min-h-0 flex-1 overflow-hidden p-2">
                <div className="flex h-full flex-col">
                  <div className="mb-4 grid flex-shrink-0 grid-cols-2 gap-4">
                    <div>
                      <p className="mb-1 text-sm font-medium">Trace ID</p>
                      <div className="flex items-center gap-1">
                        <p className="text-sm" title={selectedSpan.trace_id}>
                          {selectedSpan.trace_id
                            ? `${selectedSpan.trace_id.substring(0, 8)}...`
                            : ''}
                        </p>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(selectedSpan.trace_id);
                            toast({
                              title: 'Copied to clipboard',
                              description: 'Trace ID has been copied to clipboard',
                              duration: 2000,
                            });
                          }}
                          className="ml-1 rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus:outline-none"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="feather feather-copy"
                          >
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                          </svg>
                          <span className="sr-only">Copy trace ID</span>
                        </button>
                      </div>
                    </div>
                    <div>
                      <p className="mb-1 text-sm font-medium">Duration</p>
                      <p>
                        {formatDuration(
                          (selectedSpan.end_time
                            ? new Date(selectedSpan.end_time)
                            : new Date()
                          ).getTime() - new Date(selectedSpan.start_time).getTime()
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="mb-1 text-sm font-medium">Start Time</p>
                      <p>{formatTime(new Date(selectedSpan.start_time))}</p>
                    </div>
                    <div>
                      <p className="mb-1 text-sm font-medium">End Time</p>
                      <p>
                        {selectedSpan.end_time
                          ? formatTime(new Date(selectedSpan.end_time))
                          : 'Ongoing'}
                      </p>
                    </div>
                    {selectedSpan.parent_id && (
                      <>
                        <div>
                          <p className="mb-1 text-sm font-medium">Parent ID</p>
                          {/* Check if parent span exists in the data */}
                          {spans.some(span => span.id === selectedSpan.parent_id) ? (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => {
                                  const parentSpan = spans.find(
                                    span => span.id === selectedSpan.parent_id
                                  );
                                  if (parentSpan) {
                                    handleSpanSelect(parentSpan);
                                  }
                                }}
                                className="flex items-center rounded bg-blue-100 px-2 py-0.5 text-left text-sm text-blue-700 transition-colors hover:bg-blue-200 focus:outline-none"
                              >
                                <span
                                  className="truncate"
                                  title={
                                    spans.find(span => span.id === selectedSpan.parent_id)
                                      ?.name || selectedSpan.parent_id
                                  }
                                >
                                  {spans.find(span => span.id === selectedSpan.parent_id)
                                    ?.name ||
                                    (selectedSpan.parent_id
                                      ? `${selectedSpan.parent_id.substring(0, 8)}...`
                                      : '')}
                                </span>
                              </button>
                              <button
                                onClick={() => {
                                  navigator.clipboard.writeText(
                                    selectedSpan.parent_id || ''
                                  );
                                  toast({
                                    title: 'Copied to clipboard',
                                    description: 'Parent ID has been copied to clipboard',
                                    duration: 2000,
                                  });
                                }}
                                className="ml-1 rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus:outline-none"
                              >
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  className="feather feather-copy"
                                >
                                  <rect
                                    x="9"
                                    y="9"
                                    width="13"
                                    height="13"
                                    rx="2"
                                    ry="2"
                                  ></rect>
                                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                                <span className="sr-only">Copy parent ID</span>
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1">
                              <p className="text-sm" title={selectedSpan.parent_id}>
                                {selectedSpan.parent_id
                                  ? `${selectedSpan.parent_id.substring(0, 8)}...`
                                  : ''}
                              </p>
                              <button
                                onClick={() => {
                                  navigator.clipboard.writeText(
                                    selectedSpan.parent_id || ''
                                  );
                                  toast({
                                    title: 'Copied to clipboard',
                                    description: 'Parent ID has been copied to clipboard',
                                    duration: 2000,
                                  });
                                }}
                                className="ml-1 rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus:outline-none"
                              >
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  className="feather feather-copy"
                                >
                                  <rect
                                    x="9"
                                    y="9"
                                    width="13"
                                    height="13"
                                    rx="2"
                                    ry="2"
                                  ></rect>
                                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                                <span className="sr-only">Copy parent ID</span>
                              </button>
                            </div>
                          )}
                        </div>
                        <div></div> {/* Empty div to maintain grid alignment */}
                      </>
                    )}
                  </div>

                  <Tabs defaultValue="all" className="flex min-h-0 flex-1 flex-col">
                    <TabsList className="w-full flex-shrink-0">
                      <TabsTrigger value="all" className="flex-1">
                        All Data
                      </TabsTrigger>
                      <TabsTrigger value="input" className="flex-1">
                        Input
                      </TabsTrigger>
                      <TabsTrigger value="output" className="flex-1">
                        Output
                      </TabsTrigger>
                      <TabsTrigger value="data" className="flex-1">
                        Data
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent
                      value="all"
                      className="mt-2 min-h-0 flex-1 flex-col data-[state=active]:flex"
                    >
                      <div className="min-h-0 flex-1 overflow-hidden rounded-md border bg-muted">
                        <pre className="h-full overflow-y-auto whitespace-pre-wrap p-4 text-xs">
                          {JSON.stringify(
                            {
                              id: selectedSpan.id,
                              trace_id: selectedSpan.trace_id,
                              parent_id: selectedSpan.parent_id,
                              name: selectedSpan.name,
                              start_time: selectedSpan.start_time,
                              end_time: selectedSpan.end_time,
                              input: selectedSpan.input,
                              output: selectedSpan.output,
                              data: selectedSpan.data,
                            },
                            null,
                            2
                          )}
                        </pre>
                      </div>
                    </TabsContent>

                    <TabsContent
                      value="input"
                      className="mt-2 min-h-0 flex-1 flex-col data-[state=active]:flex"
                    >
                      <div className="min-h-0 flex-1 overflow-hidden rounded-md border bg-muted">
                        <pre className="h-full overflow-y-auto whitespace-pre-wrap p-4 text-xs">
                          {selectedSpan.input
                            ? JSON.stringify(selectedSpan.input, null, 2)
                            : 'No input data'}
                        </pre>
                      </div>
                    </TabsContent>

                    <TabsContent
                      value="output"
                      className="mt-2 min-h-0 flex-1 flex-col data-[state=active]:flex"
                    >
                      <div className="min-h-0 flex-1 overflow-hidden rounded-md border bg-muted">
                        <pre className="h-full overflow-y-auto whitespace-pre-wrap p-4 text-xs">
                          {selectedSpan.output
                            ? JSON.stringify(selectedSpan.output, null, 2)
                            : 'No output data'}
                        </pre>
                      </div>
                    </TabsContent>

                    <TabsContent
                      value="data"
                      className="mt-2 min-h-0 flex-1 flex-col data-[state=active]:flex"
                    >
                      <div className="min-h-0 flex-1 overflow-hidden rounded-md border bg-muted">
                        <pre className="h-full overflow-y-auto whitespace-pre-wrap p-4 text-xs">
                          {selectedSpan.data
                            ? JSON.stringify(selectedSpan.data, null, 2)
                            : 'No data'}
                        </pre>
                      </div>
                    </TabsContent>
                  </Tabs>
                </div>
              </CardContent>
            </>
          ) : (
            <div className="flex h-full items-center justify-center p-8">
              <div className="text-center">
                <div className="mb-4 text-muted-foreground">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="40"
                    height="40"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="mx-auto mb-2"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <path d="M8 12h8" />
                  </svg>
                </div>
                <h3 className="mb-2 text-lg font-medium">No span selected</h3>
                <p className="max-w-[300px] text-sm text-muted-foreground">
                  Click on a span in the timeline or a label in the left sidebar to view
                  its details here.
                </p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}
