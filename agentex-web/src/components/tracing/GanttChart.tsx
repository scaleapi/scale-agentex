'use client';

import type React from 'react';

import {useMemo, useState, useRef, useEffect} from 'react';
import {cn} from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {ChevronDown, ChevronRight} from 'lucide-react';

export interface Span {
  id: string;
  trace_id: string;
  parent_id?: string | null;
  name: string;
  start_time: string | Date; // Can be ISO string or Date object
  end_time?: string | Date | null; // Can be ISO string or Date object
  input?: Record<string, any> | Array<Record<string, any>> | null;
  output?: Record<string, any> | Array<Record<string, any>> | null;
  data?: Record<string, any> | Array<Record<string, any>> | null;
  type?: string; // Added for visualization purposes
  level?: number; // Added for hierarchy visualization
  children?: Span[]; // Added for hierarchy visualization
  expanded?: boolean; // Added for UI state
}

export type TraceSpan = Span;

interface GanttChartProps {
  spans: Span[];
  onSpanSelect: (span: Span) => void;
  selectedSpanId?: string;
  autoScrollToBottom?: boolean; // New prop for auto-scrolling
}

export function GanttChart({
  spans,
  onSpanSelect,
  selectedSpanId,
  autoScrollToBottom = false,
}: GanttChartProps) {
  const [timelinePosition, setTimelinePosition] = useState<number | null>(null);
  const timelineContainerRef = useRef<HTMLDivElement>(null);

  // Process spans to build hierarchy and calculate levels
  const processedSpans = useMemo(() => {
    // Create a map of id to span for quick lookup
    const spanMap = new Map<string, Span>();

    // First pass: add all spans to the map and convert dates
    spans.forEach(span => {
      // Ensure start_time and end_time are Date objects
      const startTime =
        span.start_time instanceof Date ? span.start_time : new Date(span.start_time);

      const endTime = span.end_time
        ? span.end_time instanceof Date
          ? span.end_time
          : new Date(span.end_time)
        : new Date(); // If end_time is null, use current time (span is ongoing)

      // Infer type from name if not provided
      const type = span.type || inferTypeFromName(span.name);

      spanMap.set(span.id, {
        ...span,
        start_time: startTime,
        end_time: endTime,
        type,
        children: [],
        level: 0,
        expanded: true,
      });
    });

    // Second pass: build parent-child relationships
    const rootSpans: Span[] = [];

    spans.forEach(span => {
      const processedSpan = spanMap.get(span.id)!;

      if (span.parent_id && spanMap.has(span.parent_id)) {
        const parent = spanMap.get(span.parent_id)!;
        if (!parent.children) parent.children = [];
        parent.children.push(processedSpan);
      } else {
        rootSpans.push(processedSpan);
      }
    });

    // Third pass: calculate levels (depth) for each span
    const calculateLevels = (span: Span, level: number) => {
      span.level = level;
      if (span.children) {
        span.children.forEach(child => calculateLevels(child, level + 1));
      }
    };

    rootSpans.forEach(span => calculateLevels(span, 0));

    // Fourth pass: flatten the hierarchy for rendering, respecting expanded state
    const flattenedSpans: Span[] = [];

    const flattenHierarchy = (span: Span) => {
      flattenedSpans.push(span);

      if (span.expanded && span.children && span.children.length > 0) {
        // Sort children by start time before adding them
        const sortedChildren = [...span.children].sort((a, b) => {
          const aTime =
            a.start_time instanceof Date
              ? a.start_time.getTime()
              : new Date(a.start_time).getTime();
          const bTime =
            b.start_time instanceof Date
              ? b.start_time.getTime()
              : new Date(b.start_time).getTime();
          return aTime - bTime;
        });

        sortedChildren.forEach(child => flattenHierarchy(child));
      }
    };

    // Sort root spans by start time before flattening
    const sortedRootSpans = [...rootSpans].sort((a, b) => {
      const aTime =
        a.start_time instanceof Date
          ? a.start_time.getTime()
          : new Date(a.start_time).getTime();
      const bTime =
        b.start_time instanceof Date
          ? b.start_time.getTime()
          : new Date(b.start_time).getTime();
      return aTime - bTime;
    });

    sortedRootSpans.forEach(span => flattenHierarchy(span));

    return {
      flattenedSpans,
      spanMap,
      rootSpans,
    };
  }, [spans]);

  // Infer a type from the span name for visualization purposes
  function inferTypeFromName(name: string): string {
    name = name.toLowerCase();
    if (name.includes('query')) return 'query';
    if (name.includes('search')) return 'search';
    if (name.includes('retrieval') || name.includes('lookup')) return 'knowledge';
    if (name.includes('auth')) return 'auth';
    if (name.includes('process') || name.includes('image')) return 'processing';
    if (name.includes('generat')) return 'generation';
    if (
      name.includes('reason') ||
      name.includes('understand') ||
      name.includes('planning')
    )
      return 'reasoning';
    if (name.includes('cache')) return 'cache';
    return 'default';
  }

  // Calculate the min and max times to set the chart boundaries with a fixed time-to-pixel ratio
  const {minTime, maxTime, duration, timeToPixelRatio, chartWidthPx} = useMemo(() => {
    if (!spans.length)
      return {
        minTime: new Date(),
        maxTime: new Date(),
        duration: 0,
        timeToPixelRatio: 0.25, // 4ms per pixel (0.25px per ms)
        chartWidthPx: 1200,
      };

    const startTimes = spans.map(s =>
      s.start_time instanceof Date ? s.start_time : new Date(s.start_time)
    );
    const endTimes = spans.map(s => {
      if (!s.end_time) return new Date(); // If no end time, use current time
      return s.end_time instanceof Date ? s.end_time : new Date(s.end_time);
    });

    const minTime = new Date(Math.min(...startTimes.map(d => d.getTime())));
    const maxTime = new Date(Math.max(...endTimes.map(d => d.getTime())));
    const duration = maxTime.getTime() - minTime.getTime();

    // Fixed ratio: 0.25px per ms (4ms per pixel)
    const timeToPixelRatio = 0.25;

    // Calculate required chart width based on time range and ratio
    const chartWidthPx = Math.max(duration * timeToPixelRatio, 1200);

    return {minTime, maxTime, duration, timeToPixelRatio, chartWidthPx};
  }, [spans]);

  // Get a color based on span type or inherit from parent
  const getSpanColor = (span: Span): string => {
    // Define a more diverse color palette
    const colorPalette = [
      'bg-blue-500',
      'bg-emerald-500',
      'bg-purple-500',
      'bg-amber-500',
      'bg-rose-500',
      'bg-indigo-500',
      'bg-teal-500',
      'bg-pink-500',
      'bg-orange-500',
      'bg-cyan-500',
      'bg-lime-500',
      'bg-fuchsia-500',
    ];

    // If span has a parent, use the parent's color
    if (span.parent_id) {
      const parentSpan = processedSpans.spanMap.get(span.parent_id);
      if (parentSpan) {
        // Get the parent's color (recursively if needed)
        return getSpanColor(parentSpan);
      }
    }

    // For top-level spans (no parent), assign a color based on span type or name
    // This ensures consistent coloring across refreshes
    const hash = (str: string) => {
      let hash = 0;
      for (let i = 0; i < str.length; i++) {
        hash = (hash << 5) - hash + str.charCodeAt(i);
        hash = hash & hash; // Convert to 32bit integer
      }
      return Math.abs(hash);
    };

    // Use a combination of trace_id and name to generate a consistent color index
    const colorSeed = span.type || span.name;
    const colorIndex = hash(colorSeed) % colorPalette.length;

    return colorPalette[colorIndex];
  };

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

  // Format data preview for tooltip (simplified version of the data)
  const formatDataPreview = (data: any) => {
    if (!data) return 'No data';

    try {
      // For objects, show a simplified version
      if (typeof data === 'object') {
        // Create a simplified version with just the keys and simple values
        const preview: Record<string, any> = {};

        // Get the top-level keys (limit to first 5 for brevity)
        const keys = Object.keys(data).slice(0, 5);

        keys.forEach(key => {
          const value = data[key];
          if (typeof value === 'object' && value !== null) {
            // For nested objects/arrays, just show type and size
            if (Array.isArray(value)) {
              preview[key] = `[Array: ${value.length} items]`;
            } else {
              preview[key] = `{Object: ${Object.keys(value).length} properties}`;
            }
          } else {
            // For primitive values, show the actual value
            preview[key] = value;
          }
        });

        // If there are more keys than we're showing, indicate that
        if (Object.keys(data).length > keys.length) {
          preview['...'] = `(${Object.keys(data).length - keys.length} more properties)`;
        }

        return JSON.stringify(preview, null, 2);
      }

      // For primitive values, just return as string
      return String(data);
    } catch (e) {
      return 'Error formatting data';
    }
  };

  // Toggle the expanded state of a span
  const toggleExpanded = (spanId: string) => {
    const span = processedSpans.spanMap.get(spanId);
    if (span && span.children && span.children.length > 0) {
      span.expanded = !span.expanded;
      // Force a re-render
      // In a real app, you'd use state management here
      document.getElementById(spanId)?.classList.toggle('expanded');
    }
  };

  // Handle mouse move to update timeline position
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    setTimelinePosition(x);
  };

  // Handle mouse leave to hide timeline
  const handleMouseLeave = () => {
    setTimelinePosition(null);
  };

  // Calculate time at timeline position
  const getTimeAtPosition = (position: number) => {
    if (!position) return null;

    const chartWidth = document.querySelector('.chart-container')?.clientWidth || 0;
    if (chartWidth === 0) return null;

    const percentage = position / chartWidth;
    const timeMs = minTime.getTime() + percentage * duration;
    return new Date(timeMs);
  };

  const timeAtPosition = timelinePosition ? getTimeAtPosition(timelinePosition) : null;

  // Function to scroll to a specific span
  const scrollToSpan = (span: Span) => {
    if (!timelineContainerRef.current) return;

    const startTime =
      span.start_time instanceof Date ? span.start_time : new Date(span.start_time);

    // Calculate the pixel position where this span starts
    const startOffset = (startTime.getTime() - minTime.getTime()) * timeToPixelRatio;

    // Get the width of the visible container
    const containerWidth = timelineContainerRef.current.clientWidth;

    // Center the span in the container
    const scrollPosition = Math.max(0, startOffset - containerWidth / 2);

    // Scroll to the position with smooth animation
    timelineContainerRef.current.scrollTo({
      left: scrollPosition,
      behavior: 'smooth',
    });
  };

  // Effect to scroll to selected span when it changes
  useEffect(() => {
    if (selectedSpanId && processedSpans.spanMap.has(selectedSpanId)) {
      const selectedSpan = processedSpans.spanMap.get(selectedSpanId)!;
      // Add a small delay to ensure the DOM is ready
      setTimeout(() => scrollToSpan(selectedSpan), 100);
    }
  }, [selectedSpanId]);

  // Animated scrolling function with smooth easing
  const animateScroll = (
    element: HTMLElement,
    options: {left?: number; top?: number; duration: number}
  ) => {
    if (!element) return;

    const startTime = performance.now();
    const startLeft = element.scrollLeft;
    const startTop = element.scrollTop;
    const targetLeft = options.left !== undefined ? options.left : startLeft;
    const targetTop = options.top !== undefined ? options.top : startTop;
    const duration = options.duration; // ms

    const step = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Smooth easing function - subtle ease out
      const easeOutQuint = (t: number) => 1 - Math.pow(1 - t, 5);

      if (options.left !== undefined) {
        element.scrollLeft =
          startLeft + (targetLeft - startLeft) * easeOutQuint(progress);
      }

      if (options.top !== undefined) {
        element.scrollTop = startTop + (targetTop - startTop) * easeOutQuint(progress);
      }

      if (progress < 1) {
        requestAnimationFrame(step);
      }
    };

    requestAnimationFrame(step);
  };

  // Function to scroll to the bottom and right of the timeline
  const scrollToBottom = () => {
    if (!timelineContainerRef.current) return;

    // Find the main containers that need to be scrolled
    const timelineContainer = timelineContainerRef.current;

    // Get parent container - the direct overflow-y-auto parent
    const parentContainer = timelineContainer.closest('.overflow-y-auto') as HTMLElement;

    // Calculate the maximum scroll positions
    const maxHorizontalScroll =
      timelineContainer.scrollWidth - timelineContainer.clientWidth;

    // First scroll horizontally with a very slow animation (4000ms = 4 seconds)
    animateScroll(timelineContainer, {
      left: maxHorizontalScroll,
      duration: 4000,
    });

    // Then scroll vertically if needed
    if (parentContainer) {
      // Delay the vertical scroll to start after the horizontal scroll has begun
      setTimeout(() => {
        const maxVerticalScroll =
          parentContainer.scrollHeight - parentContainer.clientHeight;

        animateScroll(parentContainer, {
          top: maxVerticalScroll,
          duration: 3500,
        });
      }, 800);
    }

    // For safety, also try to scroll the main page container if it exists
    // This handles cases where the chart is embedded in a larger scrollable page
    const mainContainer =
      document.querySelector('main') || document.querySelector('.h-screen');
    if (mainContainer && mainContainer instanceof HTMLElement) {
      setTimeout(() => {
        // Check if it's scrollable
        const isScrollable = mainContainer.scrollHeight > mainContainer.clientHeight;
        if (isScrollable) {
          animateScroll(mainContainer, {
            top: mainContainer.scrollHeight,
            duration: 3000,
          });
        }
      }, 1200);
    }
  };

  // Effect to scroll to the bottom when spans change if autoScrollToBottom is true
  useEffect(() => {
    if (autoScrollToBottom && spans.length > 0) {
      // Longer delay to ensure the DOM is fully updated with new spans
      const scrollDelay = 1000; // 1 second delay for a more deliberate feel
      setTimeout(scrollToBottom, scrollDelay);
    }
  }, [spans, autoScrollToBottom]);

  if (spans.length === 0) {
    return (
      <div className="flex h-full items-center justify-center rounded-md border">
        <p className="text-muted-foreground">No span data available</p>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="relative flex h-full flex-col">
        {/* Time scale header */}
        <div className="mb-2 flex flex-shrink-0">
          {/* Fixed space for the left column */}
          <div style={{width: '250px'}}></div>
          <div className="relative flex-1 overflow-hidden px-4 pr-8">
            {/* Multiple time markers */}
            <div className="flex w-full justify-between">
              <span className="text-xs text-muted-foreground">{formatTime(minTime)}</span>
              <span className="text-xs text-muted-foreground">{formatTime(maxTime)}</span>
            </div>

            {/* Generate time markers between min and max */}
            <div className="absolute bottom-0 left-4 right-8 h-[12px]">
              {duration > 100 &&
                Array.from({length: 5}).map((_, i) => {
                  if (i === 0 || i === 4) return null; // Skip first and last as they're already displayed

                  const timeOffset = duration * (i / 4);
                  const markerTime = new Date(minTime.getTime() + timeOffset);
                  const markerPosition = `${i * 25}%`;

                  return (
                    <div
                      key={`marker-${i}`}
                      className="absolute"
                      style={{left: markerPosition}}
                    >
                      <div className="h-1 w-[1px] bg-gray-300" />
                      <span className="mt-1 -translate-x-1/2 transform text-xs text-muted-foreground">
                        {formatTime(markerTime)}
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>

        {/* Main content container */}
        <div className="flex-1 overflow-hidden rounded-md border">
          {/* Single scrollable container for both sections */}
          <div className="h-full overflow-y-auto">
            {/* Fixed content wrapper with min-height to ensure all spans are visible */}
            <div className="flex min-h-full">
              {/* Left sidebar for span names */}
              <div className="relative w-[250px] bg-background">
                {/* Shadow effect */}
                <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-[10px] shadow-[4px_0_10px_-3px_rgba(0,0,0,0.1)]"></div>
                {/* Span names content */}
                <div className="h-full p-4">
                  {processedSpans.flattenedSpans.map((span, index) => {
                    const level = span.level || 0;
                    const hasChildren = span.children && span.children.length > 0;
                    const isSelected = selectedSpanId === span.id;

                    return (
                      <div
                        key={`label-${span.id}`}
                        className={cn(
                          'group relative mb-3 flex items-center rounded',
                          isSelected
                            ? 'bg-blue-100 text-blue-900 dark:bg-blue-800 dark:text-blue-100'
                            : 'hover:bg-gray-50 hover:text-black dark:hover:bg-gray-50 dark:hover:text-black'
                        )}
                        data-span-id={span.id}
                        style={{height: '28px'}}
                        onClick={e => {
                          // Ensure no event propagation issues
                          e.stopPropagation();
                          // Only call the callback, nothing else
                          onSpanSelect(span);
                          scrollToSpan(span);
                        }}
                        onMouseEnter={() => {
                          // Only add hover highlight if not selected
                          if (!isSelected) {
                            document
                              .querySelector(`[data-bar-id="${span.id}"]`)
                              ?.classList.add('bg-gray-50', 'text-black');
                            document
                              .querySelector(`[data-bar-id="${span.id}"]`)
                              ?.classList.remove('bg-white');
                          }
                        }}
                        onMouseLeave={() => {
                          // Only remove hover highlight if not selected
                          if (!isSelected) {
                            document
                              .querySelector(`[data-bar-id="${span.id}"]`)
                              ?.classList.remove('bg-gray-50', 'text-black');
                          }
                        }}
                      >
                        <div
                          className="flex h-full w-full cursor-pointer items-center truncate text-sm font-medium"
                          style={{paddingLeft: `${level * 16 + 16}px`}}
                        >
                          {hasChildren && (
                            <button
                              onClick={e => {
                                e.stopPropagation(); // Prevent span selection when clicking the expand button
                                toggleExpanded(span.id);
                              }}
                              className="mr-1 rounded p-0.5 hover:bg-muted"
                            >
                              {span.expanded ? (
                                <ChevronDown className="h-3 w-3" />
                              ) : (
                                <ChevronRight className="h-3 w-3" />
                              )}
                            </button>
                          )}
                          {!hasChildren && level > 0 && <span className="w-4" />}
                          <span className="truncate" title={span.name}>
                            {span.name}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right side timeline with horizontal scroll */}
              <div className="flex-1 overflow-x-auto" ref={timelineContainerRef}>
                <div
                  className="chart-container relative min-h-full p-4 pr-8"
                  style={{minWidth: `${chartWidthPx}px`}}
                  onMouseMove={handleMouseMove}
                  onMouseLeave={handleMouseLeave}
                >
                  {/* Vertical timeline indicator */}
                  {timelinePosition !== null && (
                    <div
                      className="pointer-events-none absolute bottom-0 top-0 z-10 w-[1px] bg-red-500"
                      style={{left: `${timelinePosition}px`}}
                    >
                      {timeAtPosition && (
                        <div className="absolute left-0 top-0 -translate-x-1/2 transform rounded bg-red-500 px-1 py-0.5 text-xs text-white">
                          {formatTime(timeAtPosition)}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Timeline spans */}
                  {processedSpans.flattenedSpans.map((span, index) => {
                    const startTime =
                      span.start_time instanceof Date
                        ? span.start_time
                        : new Date(span.start_time);
                    const endTime = span.end_time
                      ? span.end_time instanceof Date
                        ? span.end_time
                        : new Date(span.end_time)
                      : new Date(); // If end_time is null, use current time (span is ongoing)

                    const spanDuration = endTime.getTime() - startTime.getTime();

                    // Calculate exact pixel positions based on time
                    const startOffset =
                      (startTime.getTime() - minTime.getTime()) * timeToPixelRatio;
                    const barWidth = Math.max(spanDuration * timeToPixelRatio, 1); // At least 1px wide

                    // Convert to percentage for positioning (based on the calculated chart width)
                    const left = (startOffset / chartWidthPx) * 100;
                    const width = (barWidth / chartWidthPx) * 100;

                    const isSelected = selectedSpanId === span.id;

                    return (
                      <div
                        key={`bar-${span.id}`}
                        className={cn(
                          'relative mb-3 flex items-center rounded',
                          isSelected
                            ? 'bg-blue-100 text-blue-900 dark:bg-blue-800 dark:text-blue-100'
                            : 'hover:bg-gray-50 hover:text-black dark:hover:bg-gray-50 dark:hover:text-black'
                        )}
                        data-bar-id={span.id}
                        style={{height: '28px'}}
                        onClick={e => {
                          // Ensure no event propagation issues
                          e.stopPropagation();
                          // Only call the callback, nothing else
                          onSpanSelect(span);
                          scrollToSpan(span);
                        }}
                        onMouseEnter={() => {
                          // Only add hover highlight if not selected
                          if (!isSelected) {
                            document
                              .querySelector(`[data-span-id="${span.id}"]`)
                              ?.classList.add('bg-gray-50', 'text-black');
                            document
                              .querySelector(`[data-span-id="${span.id}"]`)
                              ?.classList.remove('bg-white');
                          }
                        }}
                        onMouseLeave={() => {
                          // Only remove hover highlight if not selected
                          if (!isSelected) {
                            document
                              .querySelector(`[data-span-id="${span.id}"]`)
                              ?.classList.remove('bg-gray-50', 'text-black');
                          }
                        }}
                      >
                        <div className="flex h-full flex-1 items-center">
                          <div
                            className={cn(
                              'flex cursor-pointer items-center justify-center rounded px-1 text-xs text-white transition-opacity hover:opacity-80',
                              getSpanColor(span)
                            )}
                            style={{
                              position: 'absolute',
                              left: `${left}%`,
                              width: `${width}%`,
                              height: '18px', // Fixed height for the colored bars
                              top: '50%',
                              transform: 'translateY(-50%)', // Perfect vertical centering
                            }}
                          >
                            {barWidth > 15 && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="truncate">
                                    {formatDuration(spanDuration)}
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent side="top">
                                  <div className="text-xs">
                                    <div>Start: {formatTime(startTime)}</div>
                                    <div>End: {formatTime(endTime)}</div>
                                    <div>Duration: {formatDuration(spanDuration)}</div>
                                  </div>
                                </TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
