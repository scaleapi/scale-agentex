'use client';

import { useMemo, useState } from 'react';

import { Bot, CalendarClock, Loader2 } from 'lucide-react';

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
          getNextRunTime(item.schedule) == null
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
  const value =
    scope === ScheduleScope.ALL ? ScheduleScope.ALL : selectedAgent?.name;

  return (
    <Select
      {...(value ? { value } : {})}
      onValueChange={nextValue => {
        if (nextValue === ScheduleScope.ALL) {
          onChange(ScheduleScope.ALL);
          return;
        }
        onSelectAgent(nextValue);
      }}
    >
      <SelectTrigger
        className="max-w-80 min-w-64"
        aria-label="Schedule agent scope"
      >
        <SelectValue placeholder="Select an agent" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ScheduleScope.ALL}>
          <span className="flex items-center gap-2">
            <CalendarClock className="size-4" />
            All agents
          </span>
        </SelectItem>
        {agents.map(agent => (
          <SelectItem key={agent.id} value={agent.name}>
            <span className="flex items-center gap-2">
              <Bot className="size-4" />
              {agent.name}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
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
