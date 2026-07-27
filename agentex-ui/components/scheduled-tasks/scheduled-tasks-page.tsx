'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { Bot, CalendarClock, ChevronDown, Loader2, Search } from 'lucide-react';

import { useAgentexClient } from '@/components/providers';
import { AllSchedulesList } from '@/components/scheduled-tasks/all-schedules-list';
import { ScheduleComposer } from '@/components/scheduled-tasks/schedule-composer';
import type {
  ScheduleListItem,
  ScheduleView,
} from '@/components/scheduled-tasks/schedule-helpers';
import {
  getNextRunTime,
  isSchedulePaused,
  sortScheduleItems,
} from '@/components/scheduled-tasks/schedule-helpers';
import { UpcomingScheduleList } from '@/components/scheduled-tasks/upcoming-schedule-list';
import { useAgentByName } from '@/hooks/use-agent-by-name';
import {
  SCHEDULE_LIST_LIMIT,
  useAgentRunSchedules,
  useAgentRunSchedulesForAgents,
} from '@/hooks/use-agent-run-schedules';
import { useAgents } from '@/hooks/use-agents';
import {
  ScheduleScope,
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import { cn } from '@/lib/utils';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

export function ScheduledTasksPage() {
  const { agentName, scheduleScope, updateParams } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();
  const { data: agents = [], isLoading: agentsLoading } =
    useAgents(agentexClient);
  const { data: agentByName } = useAgentByName(agentexClient, agentName);
  const [scheduleView, setScheduleView] = useState<ScheduleView>('upcoming');
  const selectedAgent =
    agents.find(agent => agent.name === agentName) ?? agentByName ?? null;
  const agentId = selectedAgent?.id ?? null;

  const schedulesQuery = useAgentRunSchedules(agentexClient, agentId);
  const schedules = useMemo(
    () => schedulesQuery.data ?? [],
    [schedulesQuery.data]
  );
  const allScheduleQueries = useAgentRunSchedulesForAgents(
    agentexClient,
    agents,
    scheduleScope === ScheduleScope.ALL
  );

  const currentItems = useMemo<ScheduleListItem[]>(
    () =>
      selectedAgent
        ? schedules.map(schedule => ({
            agentId: selectedAgent.id,
            agentName: selectedAgent.name,
            schedule,
          }))
        : [],
    [schedules, selectedAgent]
  );

  const allItems = useMemo<ScheduleListItem[]>(
    () =>
      agents.flatMap((agent, index) =>
        (allScheduleQueries[index]?.data ?? []).map(schedule => ({
          agentId: agent.id,
          agentName: agent.name,
          schedule,
        }))
      ),
    [agents, allScheduleQueries]
  );

  const baseItems =
    scheduleScope === ScheduleScope.ALL ? allItems : currentItems;
  const unavailableLiveDataCount = useMemo(
    () =>
      baseItems.filter(
        item =>
          !isSchedulePaused(item.schedule) &&
          item.schedule.live_data_available === false
      ).length,
    [baseItems]
  );

  const visibleItems = useMemo(() => {
    const scopedItems =
      scheduleView === 'upcoming'
        ? baseItems.filter(
            item =>
              !isSchedulePaused(item.schedule) &&
              getNextRunTime(item.schedule) != null
          )
        : baseItems;
    return sortScheduleItems(scopedItems, scheduleView);
  }, [baseItems, scheduleView]);

  const isLoading =
    scheduleScope === ScheduleScope.ALL
      ? agentsLoading || allScheduleQueries.some(query => query.isLoading)
      : schedulesQuery.isLoading;
  const error =
    scheduleScope === ScheduleScope.ALL
      ? (allScheduleQueries.find(query => query.error)?.error ?? null)
      : schedulesQuery.error;
  const emptyMessage =
    scheduleView === 'upcoming'
      ? 'No upcoming scheduled runs'
      : scheduleScope === ScheduleScope.ALL
        ? 'No schedules across agents yet'
        : 'No scheduled tasks yet';

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <div className="border-border flex flex-wrap items-center justify-between gap-4 border-b px-8 py-5">
        <div>
          <h1 className="text-foreground text-xl font-semibold">
            Scheduled Tasks
          </h1>
          <p className="text-muted-foreground text-sm">
            {scheduleScope === ScheduleScope.ALL
              ? 'Browse schedules across all agents.'
              : agentName
                ? `Run ${agentName} automatically on a cadence.`
                : 'Select an agent to schedule recurring tasks.'}
          </p>
        </div>
        <ScheduleScopeSelector
          scope={scheduleScope}
          selectedAgent={selectedAgent}
          agents={agents}
          onChange={nextScope =>
            updateParams({
              [SearchParamKey.SCHEDULE_SCOPE]:
                nextScope === ScheduleScope.ALL ? ScheduleScope.ALL : null,
            })
          }
          onSelectAgent={nextAgentName => {
            updateParams({
              [SearchParamKey.SCHEDULE_SCOPE]: null,
              [SearchParamKey.AGENT_NAME]: nextAgentName,
            });
          }}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-8 py-6">
        {scheduleScope === ScheduleScope.CURRENT && !selectedAgent ? (
          <EmptyState message="Select an agent to create scheduled tasks." />
        ) : (
          <>
            {scheduleScope === ScheduleScope.CURRENT && selectedAgent && (
              <ScheduleComposer
                agentId={selectedAgent.id}
                agentexClient={agentexClient}
                schedules={schedules}
              />
            )}
            <ScheduleViewTabs view={scheduleView} onChange={setScheduleView} />
            <p className="text-muted-foreground mx-auto w-full max-w-4xl text-xs">
              Currently showing up to {SCHEDULE_LIST_LIMIT} schedules per agent.
              Support for additional schedules is coming soon.
            </p>
            {scheduleView === 'upcoming' && unavailableLiveDataCount > 0 && (
              <p
                className="border-border bg-muted/40 text-muted-foreground mx-auto w-full max-w-4xl rounded-lg border px-4 py-3 text-xs"
                role="status"
              >
                Next-run data is temporarily unavailable for{' '}
                {unavailableLiveDataCount}{' '}
                {unavailableLiveDataCount === 1 ? 'schedule' : 'schedules'}.
                Their definitions remain available under Schedules.
              </p>
            )}
            <ScheduleList
              agentexClient={agentexClient}
              items={visibleItems}
              isLoading={isLoading}
              error={error}
              emptyMessage={emptyMessage}
              showAgentName={scheduleScope === ScheduleScope.ALL}
              view={scheduleView}
            />
          </>
        )}
      </div>
    </div>
  );
}

function ScheduleScopeSelector({
  scope,
  selectedAgent,
  agents,
  onChange,
  onSelectAgent,
}: {
  scope: ScheduleScope;
  selectedAgent: Agent | null;
  agents: Agent[];
  onChange: (scope: ScheduleScope) => void;
  onSelectAgent: (agentName: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return agents;
    return agents.filter(agent =>
      agent.name.toLowerCase().includes(normalizedQuery)
    );
  }, [agents, query]);

  useEffect(() => {
    if (!isOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
        setQuery('');
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        setQuery('');
        triggerRef.current?.focus();
      }
    };

    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isOpen]);

  const selectScope = (nextScope: ScheduleScope) => {
    onChange(nextScope);
    setIsOpen(false);
    setQuery('');
    triggerRef.current?.focus();
  };

  const selectAgent = (agentName: string) => {
    onSelectAgent(agentName);
    setIsOpen(false);
    setQuery('');
    triggerRef.current?.focus();
  };

  return (
    <div ref={containerRef} className="relative max-w-80 min-w-64">
      <button
        ref={triggerRef}
        type="button"
        className="border-input focus-visible:border-primary-foreground focus-visible:ring-primary-foreground/50 flex h-9 w-full items-center justify-between gap-2 rounded-full border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
        aria-label="Schedule agent scope"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(current => !current)}
      >
        <span className="flex min-w-0 items-center gap-2">
          {scope === ScheduleScope.ALL ? (
            <CalendarClock className="size-4 shrink-0" />
          ) : (
            <Bot className="size-4 shrink-0" />
          )}
          <span className="truncate">
            {scope === ScheduleScope.ALL
              ? 'All agents'
              : (selectedAgent?.name ?? 'Select an agent')}
          </span>
        </span>
        <ChevronDown className="text-muted-foreground size-4 shrink-0" />
      </button>
      {isOpen && (
        <div className="bg-popover text-popover-foreground absolute right-0 z-50 mt-1 w-full min-w-72 rounded-md border p-1 shadow-md">
          <div className="relative p-1">
            <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <input
              autoFocus
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search agents"
              aria-label="Search agents"
              className="border-input bg-background focus-visible:border-primary-foreground focus-visible:ring-primary-foreground/50 h-9 w-full rounded-md border pr-3 pl-9 text-sm outline-none focus-visible:ring-[3px]"
            />
          </div>
          <div
            className="max-h-64 overflow-y-auto p-1"
            role="listbox"
            aria-label="Schedule agent scope"
          >
            <button
              type="button"
              role="option"
              aria-selected={scope === ScheduleScope.ALL}
              onClick={() => selectScope(ScheduleScope.ALL)}
              className="hover:bg-muted focus:bg-muted flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none"
            >
              <CalendarClock className="size-4" />
              All agents
            </button>
            {filteredAgents.map(agent => (
              <button
                key={agent.id}
                type="button"
                role="option"
                aria-selected={
                  scope === ScheduleScope.CURRENT &&
                  selectedAgent?.id === agent.id
                }
                onClick={() => selectAgent(agent.name)}
                className="hover:bg-muted focus:bg-muted flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none"
              >
                <Bot className="size-4" />
                <span className="truncate">{agent.name}</span>
              </button>
            ))}
            {query.trim() && filteredAgents.length === 0 && (
              <p className="text-muted-foreground px-2 py-3 text-center text-sm">
                No agents found
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ScheduleViewTabs({
  view,
  onChange,
}: {
  view: ScheduleView;
  onChange: (view: ScheduleView) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-3">
      <div className="border-border bg-background flex rounded-full border p-1 shadow-sm">
        {(['upcoming', 'all'] as const).map(option => (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            className={cn(
              'rounded-full px-3 py-1.5 text-sm transition-colors',
              view === option
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {option === 'upcoming' ? 'Upcoming' : 'Schedules'}
          </button>
        ))}
      </div>
    </div>
  );
}

function ScheduleList({
  agentexClient,
  items,
  isLoading,
  error,
  emptyMessage,
  showAgentName,
  view,
}: {
  agentexClient: AgentexSDK;
  items: ScheduleListItem[];
  isLoading: boolean;
  error: Error | null;
  emptyMessage: string;
  showAgentName: boolean;
  view: ScheduleView;
}) {
  if (isLoading) {
    return (
      <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
        <Loader2 className="mr-2 size-4 animate-spin" />
        Loading scheduled tasks
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState message="Scheduled tasks are unavailable. Check that schedule routes are enabled locally." />
    );
  }

  if (items.length === 0) {
    return <EmptyState message={emptyMessage} />;
  }

  if (view === 'upcoming') {
    return (
      <UpcomingScheduleList
        agentexClient={agentexClient}
        items={items}
        showAgentName={showAgentName}
      />
    );
  }

  return (
    <AllSchedulesList
      agentexClient={agentexClient}
      items={items}
      showAgentName={showAgentName}
    />
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="border-border text-muted-foreground mx-auto flex min-h-52 w-full max-w-4xl flex-col items-center justify-center rounded-2xl border border-dashed p-8 text-sm">
      <CalendarClock className="mb-3 size-8" />
      {message}
    </div>
  );
}
