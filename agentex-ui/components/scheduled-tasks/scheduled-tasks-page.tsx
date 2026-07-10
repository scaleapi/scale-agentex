'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import {
  Bot,
  CalendarClock,
  Clock3,
  Loader2,
  MoreHorizontal,
  PauseCircle,
  Pencil,
  Play,
  Trash2,
  X,
} from 'lucide-react';

import { useAgentexClient } from '@/components/providers';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from '@/components/ui/toast';
import { useAgentByName } from '@/hooks/use-agent-by-name';
import {
  useAgentRunScheduleDetailsForItems,
  useAgentRunSchedules,
  useAgentRunSchedulesForAgents,
  useCreateAgentRunSchedule,
  useScheduleAction,
  useUpdateAgentRunSchedule,
} from '@/hooks/use-agent-run-schedules';
import { useAgents } from '@/hooks/use-agents';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import type { AgentRunSchedule } from '@/lib/agent-run-schedules';
import {
  cadenceToPayload,
  DEFAULT_CADENCE,
  describeCadence,
  generateScheduleName,
  normalizeScheduleName,
  scheduleToCadence,
  type CadenceConfig,
  type CadenceType,
} from '@/lib/schedule-utils';
import { cn } from '@/lib/utils';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

type ScheduleScope = 'current' | 'all';
type ScheduleView = 'upcoming' | 'all';

type ScheduleListItem = {
  agentId: string;
  agentName: string;
  schedule: AgentRunSchedule;
};

type UpcomingRunItem = ScheduleListItem & {
  runTime: Date;
  isSkipped: boolean;
};

const DAYS = [
  ['MON', 'Monday'],
  ['TUE', 'Tuesday'],
  ['WED', 'Wednesday'],
  ['THU', 'Thursday'],
  ['FRI', 'Friday'],
  ['SAT', 'Saturday'],
  ['SUN', 'Sunday'],
] as const;

const COMMON_TIMEZONES = [
  'UTC',
  'America/Los_Angeles',
  'America/Denver',
  'America/Chicago',
  'America/New_York',
  'America/Toronto',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
] as const;

function getBrowserTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

function getNextRun(schedule: AgentRunSchedule) {
  const nextRun = schedule.next_action_times[0];
  return nextRun ? new Date(nextRun) : null;
}

function getNextRunTime(schedule: AgentRunSchedule) {
  return getNextRun(schedule)?.getTime() ?? null;
}

function getVisibleUpcomingRuns(schedule: AgentRunSchedule) {
  const now = Date.now();
  const runItems = [
    ...schedule.next_action_times.map(nextRun => ({
      runTime: new Date(nextRun),
      isSkipped: false,
    })),
    ...schedule.skipped_action_times.map(skippedRun => ({
      runTime: new Date(skippedRun),
      isSkipped: true,
    })),
  ];
  const runsByTime = new Map<string, { runTime: Date; isSkipped: boolean }>();

  for (const runItem of runItems) {
    if (runItem.runTime.getTime() >= now) {
      const key = runItem.runTime.toISOString();
      const existing = runsByTime.get(key);
      runsByTime.set(key, {
        runTime: runItem.runTime,
        isSkipped: runItem.isSkipped || existing?.isSkipped === true,
      });
    }
  }

  return Array.from(runsByTime.values())
    .sort((a, b) => a.runTime.getTime() - b.runTime.getTime())
    .slice(0, 5);
}

function isSchedulePaused(schedule: AgentRunSchedule) {
  return schedule.state === 'PAUSED' || schedule.paused;
}

function sortScheduleItems(items: ScheduleListItem[], view: ScheduleView) {
  return [...items].sort((a, b) => {
    const aNextRun = getNextRunTime(a.schedule);
    const bNextRun = getNextRunTime(b.schedule);

    if (view === 'upcoming') {
      return (aNextRun ?? 0) - (bNextRun ?? 0);
    }

    if (aNextRun != null && bNextRun != null) {
      return aNextRun - bNextRun;
    }
    if (aNextRun != null) return -1;
    if (bNextRun != null) return 1;
    return a.schedule.name.localeCompare(b.schedule.name);
  });
}

function formatRunTime(date: Date) {
  return date.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

function formatRunDateTime(date: Date) {
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function getUpcomingGroup(date: Date) {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const startOfTomorrow = new Date(startOfToday);
  startOfTomorrow.setDate(startOfToday.getDate() + 1);
  const startOfDayAfterTomorrow = new Date(startOfTomorrow);
  startOfDayAfterTomorrow.setDate(startOfTomorrow.getDate() + 1);

  if (date >= startOfToday && date < startOfTomorrow) {
    return 'Today';
  }
  if (date >= startOfTomorrow && date < startOfDayAfterTomorrow) {
    return 'Tomorrow';
  }
  return 'Later';
}

function formatUpcomingSubtitle(date: Date) {
  const group = getUpcomingGroup(date);
  if (group === 'Today') {
    return `Today, ${formatRunTime(date)}`;
  }
  if (group === 'Tomorrow') {
    return `Tomorrow, ${formatRunTime(date)}`;
  }
  return formatRunDateTime(date);
}

function groupUpcomingRuns(items: ScheduleListItem[]) {
  const groups = new Map<string, UpcomingRunItem[]>();
  for (const item of items) {
    for (const run of getVisibleUpcomingRuns(item.schedule)) {
      const group = getUpcomingGroup(run.runTime);
      groups.set(group, [...(groups.get(group) ?? []), { ...item, ...run }]);
    }
  }
  return ['Today', 'Tomorrow', 'Later']
    .map(label => ({
      label,
      items: [...(groups.get(label) ?? [])].sort(
        (a, b) => a.runTime.getTime() - b.runTime.getTime()
      ),
    }))
    .filter(group => group.items.length > 0);
}

function useCloseOnOutsideClick<T extends HTMLElement>(
  isOpen: boolean,
  onClose: () => void
) {
  const ref = useRef<T>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) {
        onClose();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  return ref;
}

export function ScheduledTasksPage() {
  const { agentName, updateParams } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();
  const { data: agents = [], isLoading: agentsLoading } =
    useAgents(agentexClient);
  const { data: agentByName } = useAgentByName(agentexClient, agentName);
  const [scope, setScope] = useState<ScheduleScope>('current');
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
    scope === 'all'
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

  const baseItems = scope === 'all' ? allItems : currentItems;
  const detailQueries = useAgentRunScheduleDetailsForItems(
    agentexClient,
    baseItems
  );
  const schedulesWithLiveFields = baseItems.map((item, index) => ({
    ...item,
    schedule: detailQueries[index]?.data ?? item.schedule,
  }));

  const visibleItems = useMemo(() => {
    const scopedItems =
      scheduleView === 'upcoming'
        ? schedulesWithLiveFields.filter(
            item =>
              !isSchedulePaused(item.schedule) &&
              getNextRunTime(item.schedule) != null
          )
        : schedulesWithLiveFields;
    return sortScheduleItems(scopedItems, scheduleView);
  }, [scheduleView, schedulesWithLiveFields]);

  const isLoading =
    scope === 'all'
      ? agentsLoading || allScheduleQueries.some(query => query.isLoading)
      : schedulesQuery.isLoading;
  const error =
    scope === 'all'
      ? (allScheduleQueries.find(query => query.error)?.error ?? null)
      : schedulesQuery.error;
  const emptyMessage =
    scheduleView === 'upcoming'
      ? 'No upcoming scheduled runs'
      : scope === 'all'
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
            {scope === 'all'
              ? 'Browse schedules across all agents.'
              : agentName
                ? `Run ${agentName} automatically on a cadence.`
                : 'Select an agent to schedule recurring tasks.'}
          </p>
        </div>
        <ScheduleScopeSelector
          scope={scope}
          selectedAgent={selectedAgent}
          agents={agents}
          onChange={setScope}
          onSelectAgent={nextAgentName => {
            setScope('current');
            updateParams({ [SearchParamKey.AGENT_NAME]: nextAgentName });
          }}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-8 py-6">
        {scope === 'current' && !selectedAgent ? (
          <EmptyState message="Select an agent to create scheduled tasks." />
        ) : (
          <>
            {scope === 'current' && selectedAgent && (
              <ScheduleComposer
                agentId={selectedAgent.id}
                agentexClient={agentexClient}
                schedules={schedules}
              />
            )}
            <ScheduleViewTabs view={scheduleView} onChange={setScheduleView} />
            <ScheduleList
              agentexClient={agentexClient}
              items={visibleItems}
              isLoading={isLoading}
              error={error}
              emptyMessage={emptyMessage}
              showAgentName={scope === 'all'}
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
  const value = scope === 'all' ? 'all' : selectedAgent?.name;

  return (
    <Select
      {...(value ? { value } : {})}
      onValueChange={nextValue => {
        if (nextValue === 'all') {
          onChange('all');
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
        <SelectItem value="all">
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
            {option === 'upcoming' ? 'Upcoming' : 'All Schedules'}
          </button>
        ))}
      </div>
    </div>
  );
}

function ScheduleComposer({
  agentId,
  agentexClient,
  schedules,
}: {
  agentId: string;
  agentexClient: AgentexSDK;
  schedules: AgentRunSchedule[];
}) {
  const [prompt, setPrompt] = useState('');
  const [cadence, setCadence] = useState<CadenceConfig>(DEFAULT_CADENCE);
  const [timezone, setTimezone] = useState(getBrowserTimezone);
  const [pendingName, setPendingName] = useState<string | null>(null);
  const createSchedule = useCreateAgentRunSchedule({
    agentexClient,
    agentId,
  });

  const handleReview = () => {
    if (!prompt.trim()) {
      toast.error('Enter a prompt to schedule');
      return;
    }
    setPendingName(generateScheduleName(prompt, schedules));
  };

  const handleCreate = async () => {
    if (!pendingName) return;
    await createSchedule.mutateAsync({
      name: pendingName,
      timezone,
      ...cadenceToPayload(cadence),
      initial_input: {
        type: 'text',
        author: 'user',
        content: prompt.trim(),
      },
    });
    setPrompt('');
    setPendingName(null);
  };

  return (
    <section className="mx-auto flex w-full max-w-4xl flex-col gap-3">
      <div className="border-input dark:bg-input flex flex-col gap-3 rounded-4xl border px-5 py-4 shadow-sm">
        <textarea
          value={prompt}
          onChange={event => setPrompt(event.target.value)}
          placeholder="What should this agent do on a schedule?"
          className="min-h-20 resize-none border-0 bg-transparent text-sm leading-6 outline-none focus:border-0 focus:ring-0 focus:outline-none focus-visible:outline-none"
        />
        <div className="flex flex-wrap items-center gap-3">
          <CadenceControls cadence={cadence} onChange={setCadence} />
          <TimezoneSelect timezone={timezone} onChange={setTimezone} />
          <Button
            onClick={handleReview}
            disabled={!prompt.trim() || createSchedule.isPending}
            className="ml-auto rounded-full"
          >
            Review Schedule
          </Button>
        </div>
      </div>
      <p className="text-muted-foreground px-4 text-xs">
        The schedule name is generated from the prompt and can be edited before
        creation.
      </p>
      {pendingName && (
        <ConfirmScheduleModal
          title="Create scheduled task"
          name={pendingName}
          setName={setPendingName}
          prompt={prompt}
          cadence={cadence}
          timezone={timezone}
          onCancel={() => setPendingName(null)}
          onConfirm={handleCreate}
          isSubmitting={createSchedule.isPending}
        />
      )}
    </section>
  );
}

function CadenceControls({
  cadence,
  onChange,
}: {
  cadence: CadenceConfig;
  onChange: (cadence: CadenceConfig) => void;
}) {
  const setField = <K extends keyof CadenceConfig>(
    key: K,
    value: CadenceConfig[K]
  ) => onChange({ ...cadence, [key]: value });

  return (
    <>
      <Select
        value={cadence.type}
        onValueChange={value => setField('type', value as CadenceType)}
      >
        <SelectTrigger className="min-w-32">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="daily">Daily</SelectItem>
          <SelectItem value="weekly">Weekly</SelectItem>
          <SelectItem value="monthly">Monthly</SelectItem>
          <SelectItem value="interval">Interval</SelectItem>
        </SelectContent>
      </Select>

      {cadence.type !== 'interval' ? (
        <input
          type="time"
          value={cadence.time}
          onChange={event => setField('time', event.target.value)}
          className="border-input bg-background h-9 rounded-full border px-3 text-sm"
          aria-label="Schedule time"
        />
      ) : (
        <>
          <input
            value={cadence.intervalValue}
            onChange={event => setField('intervalValue', event.target.value)}
            className="border-input bg-background h-9 w-20 rounded-full border px-3 text-sm"
            aria-label="Interval value"
          />
          <Select
            value={cadence.intervalUnit}
            onValueChange={value =>
              setField('intervalUnit', value as CadenceConfig['intervalUnit'])
            }
          >
            <SelectTrigger className="min-w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="minutes">Minutes</SelectItem>
              <SelectItem value="hours">Hours</SelectItem>
              <SelectItem value="days">Days</SelectItem>
            </SelectContent>
          </Select>
        </>
      )}

      {cadence.type === 'weekly' && (
        <Select
          value={cadence.dayOfWeek}
          onValueChange={value => setField('dayOfWeek', value)}
        >
          <SelectTrigger className="min-w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DAYS.map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {cadence.type === 'monthly' && (
        <input
          value={cadence.dayOfMonth}
          onChange={event => setField('dayOfMonth', event.target.value)}
          className="border-input bg-background h-9 w-24 rounded-full border px-3 text-sm"
          aria-label="Day of month"
          placeholder="Day"
        />
      )}
    </>
  );
}

function TimezoneSelect({
  timezone,
  onChange,
}: {
  timezone: string;
  onChange: (timezone: string) => void;
}) {
  const timezoneOptions = useMemo(() => {
    const options = new Set<string>([timezone, getBrowserTimezone()]);

    for (const commonTimezone of COMMON_TIMEZONES) {
      options.add(commonTimezone);
    }

    return Array.from(options).filter(Boolean);
  }, [timezone]);

  return (
    <Select value={timezone} onValueChange={onChange}>
      <SelectTrigger className="min-w-52">
        <SelectValue placeholder="Timezone" />
      </SelectTrigger>
      <SelectContent>
        {timezoneOptions.map(option => (
          <SelectItem key={option} value={option}>
            {option.replace('_', ' ')}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
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

function UpcomingScheduleList({
  agentexClient,
  items,
  showAgentName,
}: {
  agentexClient: AgentexSDK;
  items: ScheduleListItem[];
  showAgentName: boolean;
}) {
  const groupedItems = groupUpcomingRuns(items);

  return (
    <section className="mx-auto w-full max-w-4xl">
      <div className="flex flex-col gap-6">
        {groupedItems.map(group => (
          <div key={group.label} className="grid grid-cols-[5rem_1fr] gap-6">
            <div className="text-muted-foreground pt-1 text-sm font-medium">
              {group.label}
            </div>
            <div className="before:bg-border relative flex flex-col gap-5 pl-8 before:absolute before:top-2 before:bottom-2 before:left-1 before:w-px">
              {group.items.map(item => (
                <UpcomingScheduleRow
                  key={`${item.schedule.id}-${item.runTime.toISOString()}`}
                  agentexClient={agentexClient}
                  item={item}
                  showAgentName={showAgentName}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function UpcomingScheduleRow({
  agentexClient,
  item,
  showAgentName,
}: {
  agentexClient: AgentexSDK;
  item: UpcomingRunItem;
  showAgentName: boolean;
}) {
  const { agentId, agentName, schedule } = item;
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isRunModalOpen, setIsRunModalOpen] = useState(false);
  const trigger = useScheduleAction({
    agentexClient,
    agentId,
    action: 'trigger',
  });
  const skip = useScheduleAction({
    agentexClient,
    agentId,
    action: 'skip',
  });
  const unskip = useScheduleAction({
    agentexClient,
    agentId,
    action: 'unskip',
  });

  return (
    <div className="relative flex items-center justify-between gap-4">
      <span className="absolute top-2 -left-8 z-10 size-2 rounded-full bg-[#7C5CFF]" />
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold">{schedule.name}</div>
        <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
          <span>{formatUpcomingSubtitle(item.runTime)}</span>
          {showAgentName && <span>· {agentName}</span>}
          {item.isSkipped && (
            <span className="rounded-full bg-[#7C5CFF]/10 px-2 py-0.5 text-xs font-medium text-[#6F4DFF]">
              Skipped
            </span>
          )}
        </div>
      </div>
      <div className="relative flex shrink-0 items-center gap-2">
        {item.isSkipped ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              unskip.mutate({
                scheduleId: schedule.id,
                scheduledTime: item.runTime.toISOString(),
              })
            }
            disabled={unskip.isPending}
          >
            Unskip
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsRunModalOpen(true)}
          >
            <Play className="size-4" />
            Run now
          </Button>
        )}
        {isRunModalOpen && (
          <RunNowModal
            schedule={schedule}
            runTime={item.runTime}
            onClose={() => setIsRunModalOpen(false)}
            onRunNow={() => {
              setIsRunModalOpen(false);
              trigger.mutate(schedule.id);
            }}
            onRunNowAndSkip={() => {
              setIsRunModalOpen(false);
              void (async () => {
                await trigger.mutateAsync(schedule.id);
                await skip.mutateAsync({
                  scheduleId: schedule.id,
                  scheduledTime: item.runTime.toISOString(),
                });
              })().catch(() => undefined);
            }}
            isRunNowPending={trigger.isPending}
            isRunNowAndSkipPending={trigger.isPending || skip.isPending}
          />
        )}
        <ScheduleOverflowMenu
          isOpen={isMenuOpen}
          setIsOpen={setIsMenuOpen}
          schedule={schedule}
          agentexClient={agentexClient}
          agentId={agentId}
          includeRunNow={false}
          scheduledTime={item.runTime.toISOString()}
          isSkipped={item.isSkipped}
        />
      </div>
    </div>
  );
}

function RunNowModal({
  schedule,
  runTime,
  onClose,
  onRunNow,
  onRunNowAndSkip,
  isRunNowPending,
  isRunNowAndSkipPending,
}: {
  schedule: AgentRunSchedule;
  runTime: Date;
  onClose: () => void;
  onRunNow: () => void;
  onRunNowAndSkip: () => void;
  isRunNowPending: boolean;
  isRunNowAndSkipPending: boolean;
}) {
  const runLabel = formatUpcomingSubtitle(runTime);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="bg-background w-full max-w-md rounded-2xl border p-5 shadow-xl">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Run task now</h2>
            <p className="text-muted-foreground mt-1 text-sm">
              Choose how to handle the scheduled run at {runLabel}.
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="flex flex-col gap-2">
          <RunNowOption
            title="Run now"
            description={`Runs ${schedule.name} once right now. The scheduled run at ${runLabel} still happens as planned.`}
            onClick={onRunNow}
            disabled={isRunNowPending}
          />
          <RunNowOption
            title="Run now & skip scheduled run"
            description={`Runs once right now and skips only the scheduled run at ${runLabel}. Future scheduled runs are unchanged.`}
            onClick={onRunNowAndSkip}
            disabled={isRunNowAndSkipPending}
          />
        </div>

        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-muted-foreground text-xs">
            Skipping only affects this occurrence; the schedule remains active.
          </p>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

function RunNowOption({
  title,
  description,
  onClick,
  disabled,
}: {
  title: string;
  description: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="border-border hover:bg-muted/40 flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-colors disabled:pointer-events-none disabled:opacity-60"
    >
      <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#7C5CFF]/10 text-[#6F4DFF]">
        <Play className="size-4" />
      </span>
      <span>
        <span className="block text-sm font-semibold">{title}</span>
        <span className="text-muted-foreground mt-1 block text-sm leading-5">
          {description}
        </span>
      </span>
    </button>
  );
}

function AllSchedulesList({
  agentexClient,
  items,
  showAgentName,
}: {
  agentexClient: AgentexSDK;
  items: ScheduleListItem[];
  showAgentName: boolean;
}) {
  return (
    <section className="mx-auto w-full max-w-4xl">
      <div className="border-border overflow-visible rounded-2xl border">
        {items.map(({ agentId, agentName, schedule }) => (
          <ScheduleRow
            key={schedule.id}
            agentId={agentId}
            agentName={agentName}
            agentexClient={agentexClient}
            schedule={schedule}
            showAgentName={showAgentName}
          />
        ))}
      </div>
    </section>
  );
}

function ScheduleRow({
  agentId,
  agentName,
  agentexClient,
  schedule,
  showAgentName,
}: {
  agentId: string;
  agentName: string;
  agentexClient: AgentexSDK;
  schedule: AgentRunSchedule;
  showAgentName: boolean;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const pause = useScheduleAction({ agentexClient, agentId, action: 'pause' });
  const resume = useScheduleAction({
    agentexClient,
    agentId,
    action: 'resume',
  });
  const isPaused = isSchedulePaused(schedule);
  const nextRun = getNextRun(schedule);

  return (
    <article className="border-border/70 relative flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0">
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold">{schedule.name}</div>
        <div className="text-muted-foreground truncate text-sm">
          {describeCadence(schedule)}
          {showAgentName ? ` · ${agentName}` : ''}
          {` · ${schedule.num_actions_taken} runs`}
        </div>
      </div>
      <div className="relative flex shrink-0 items-center justify-end gap-2">
        <button
          type="button"
          onClick={() =>
            isPaused ? resume.mutate(schedule.id) : pause.mutate(schedule.id)
          }
          disabled={pause.isPending || resume.isPending}
          className={cn(
            'flex h-6 w-11 items-center rounded-full p-0.5 transition-colors disabled:opacity-60',
            isPaused ? 'bg-slate-200 dark:bg-slate-700' : 'bg-[#6F4DFF]'
          )}
          aria-label={isPaused ? 'Activate schedule' : 'Deactivate schedule'}
        >
          <span
            className={cn(
              'bg-background size-5 rounded-full shadow-sm transition-transform',
              isPaused ? 'translate-x-0' : 'translate-x-5'
            )}
          />
        </button>
        <ScheduleOverflowMenu
          isOpen={isMenuOpen}
          setIsOpen={setIsMenuOpen}
          schedule={schedule}
          agentexClient={agentexClient}
          agentId={agentId}
          onEdit={() => setIsEditing(true)}
          includeRunNow={true}
          {...(nextRun ? { scheduledTime: nextRun.toISOString() } : {})}
        />
      </div>
      {isEditing && (
        <EditScheduleModal
          agentId={agentId}
          agentexClient={agentexClient}
          schedule={schedule}
          onClose={() => setIsEditing(false)}
        />
      )}
    </article>
  );
}

function ScheduleOverflowMenu({
  isOpen,
  setIsOpen,
  schedule,
  agentexClient,
  agentId,
  onEdit,
  includeRunNow,
  scheduledTime,
  isSkipped = false,
}: {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean | ((isOpen: boolean) => boolean)) => void;
  schedule: AgentRunSchedule;
  agentexClient: AgentexSDK;
  agentId: string;
  onEdit?: () => void;
  includeRunNow: boolean;
  scheduledTime?: string;
  isSkipped?: boolean;
}) {
  const menuRef = useCloseOnOutsideClick<HTMLDivElement>(isOpen, () =>
    setIsOpen(false)
  );
  const pause = useScheduleAction({ agentexClient, agentId, action: 'pause' });
  const resume = useScheduleAction({
    agentexClient,
    agentId,
    action: 'resume',
  });
  const skip = useScheduleAction({
    agentexClient,
    agentId,
    action: 'skip',
  });
  const unskip = useScheduleAction({
    agentexClient,
    agentId,
    action: 'unskip',
  });
  const trigger = useScheduleAction({
    agentexClient,
    agentId,
    action: 'trigger',
  });
  const deleteSchedule = useScheduleAction({
    agentexClient,
    agentId,
    action: 'delete',
  });
  const isPaused = isSchedulePaused(schedule);
  const canSkip = scheduledTime != null && !isPaused;

  return (
    <div ref={menuRef} className="relative">
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setIsOpen(open => !open)}
        aria-label={`Open actions for ${schedule.name}`}
      >
        <MoreHorizontal className="size-4" />
      </Button>
      {isOpen && (
        <div className="bg-popover text-popover-foreground absolute top-10 right-0 z-50 min-w-48 rounded-md border p-1 shadow-lg">
          {includeRunNow && (
            <MenuButton
              onClick={() => {
                setIsOpen(false);
                trigger.mutate(schedule.id);
              }}
              disabled={trigger.isPending}
            >
              <Play className="size-4" />
              Run now
            </MenuButton>
          )}
          {isSkipped ? (
            <MenuButton
              onClick={() => {
                if (!scheduledTime) return;
                setIsOpen(false);
                unskip.mutate({ scheduleId: schedule.id, scheduledTime });
              }}
              disabled={unskip.isPending || !scheduledTime}
            >
              <Clock3 className="size-4" />
              Unskip run
            </MenuButton>
          ) : (
            <MenuButton
              onClick={() => {
                if (!scheduledTime) return;
                setIsOpen(false);
                skip.mutate({ scheduleId: schedule.id, scheduledTime });
              }}
              disabled={skip.isPending || !canSkip}
            >
              <Play className="size-4" />
              Skip next run
            </MenuButton>
          )}
          <MenuButton disabled title="Backend support needed">
            <Clock3 className="size-4" />
            Snooze
          </MenuButton>
          <MenuButton
            onClick={() => {
              setIsOpen(false);
              if (isPaused) {
                resume.mutate(schedule.id);
              } else {
                pause.mutate(schedule.id);
              }
            }}
            disabled={pause.isPending || resume.isPending}
          >
            <PauseCircle className="size-4" />
            {isPaused ? 'Resume' : 'Pause'}
          </MenuButton>
          {onEdit && (
            <MenuButton
              onClick={() => {
                setIsOpen(false);
                onEdit();
              }}
            >
              <Pencil className="size-4" />
              Edit
            </MenuButton>
          )}
          <MenuButton
            onClick={() => {
              setIsOpen(false);
              deleteSchedule.mutate(schedule.id);
            }}
            disabled={deleteSchedule.isPending}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="size-4" />
            Delete
          </MenuButton>
        </div>
      )}
    </div>
  );
}

function MenuButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        'hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm disabled:pointer-events-none disabled:opacity-50',
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function EditScheduleModal({
  agentId,
  agentexClient,
  schedule,
  onClose,
}: {
  agentId: string;
  agentexClient: AgentexSDK;
  schedule: AgentRunSchedule;
  onClose: () => void;
}) {
  const [name, setName] = useState(schedule.name);
  const [prompt, setPrompt] = useState(schedule.initial_input.content);
  const [cadence, setCadence] = useState(() => scheduleToCadence(schedule));
  const [timezone, setTimezone] = useState(schedule.timezone);
  const updateSchedule = useUpdateAgentRunSchedule({
    agentexClient,
    agentId,
  });

  const handleSave = async () => {
    await updateSchedule.mutateAsync({
      scheduleId: schedule.id,
      payload: {
        name,
        timezone,
        ...cadenceToPayload(cadence),
        initial_input: {
          type: 'text',
          author: 'user',
          content: prompt.trim(),
        },
      },
    });
    onClose();
  };

  return (
    <BasicModal title="Edit scheduled task" onClose={onClose}>
      <ScheduleNameInput name={name} setName={setName} />
      <textarea
        value={prompt}
        onChange={event => setPrompt(event.target.value)}
        className="border-input bg-background min-h-24 rounded-md border p-3 text-sm"
      />
      <div className="flex flex-wrap items-center gap-3">
        <CadenceControls cadence={cadence} onChange={setCadence} />
      </div>
      <TimezoneSelect timezone={timezone} onChange={setTimezone} />
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button
          onClick={handleSave}
          disabled={!name.trim() || !prompt.trim() || updateSchedule.isPending}
        >
          Save
        </Button>
      </div>
    </BasicModal>
  );
}

function ConfirmScheduleModal({
  title,
  name,
  setName,
  prompt,
  cadence,
  timezone,
  onCancel,
  onConfirm,
  isSubmitting,
}: {
  title: string;
  name: string;
  setName: (name: string) => void;
  prompt: string;
  cadence: CadenceConfig;
  timezone: string;
  onCancel: () => void;
  onConfirm: () => void;
  isSubmitting: boolean;
}) {
  const cadencePreview = useMemo(() => cadenceToPayload(cadence), [cadence]);

  return (
    <BasicModal title={title} onClose={onCancel}>
      <ScheduleNameInput name={name} setName={setName} />
      <div className="bg-muted rounded-md p-3 text-sm">
        <p className="font-medium">Prompt</p>
        <p className="text-muted-foreground mt-1 whitespace-pre-wrap">
          {prompt}
        </p>
      </div>
      <div className="text-muted-foreground text-sm">
        Cadence:{' '}
        {'cron_expression' in cadencePreview
          ? cadencePreview.cron_expression
          : `Every ${cadencePreview.interval_seconds} seconds`}
        {' · '}
        {timezone}
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={onConfirm} disabled={!name.trim() || isSubmitting}>
          Create
        </Button>
      </div>
    </BasicModal>
  );
}

function ScheduleNameInput({
  name,
  setName,
}: {
  name: string;
  setName: (name: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium">Name</span>
      <input
        value={name}
        onChange={event => setName(normalizeScheduleName(event.target.value))}
        className="border-input bg-background h-9 rounded-md border px-3"
      />
      <span className="text-muted-foreground text-xs">
        Use lowercase letters, numbers, and hyphens.
      </span>
    </label>
  );
}

function BasicModal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="bg-background w-full max-w-lg rounded-2xl border p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="flex flex-col gap-4">{children}</div>
      </div>
    </div>
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
