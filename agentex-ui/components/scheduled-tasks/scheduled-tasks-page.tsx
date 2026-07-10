'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  ArrowUp,
  Bot,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
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
  ScheduleScope,
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
  sanitizeScheduleNameInput,
  scheduleToCadence,
  type CadenceConfig,
  type CadenceType,
} from '@/lib/schedule-utils';
import { cn } from '@/lib/utils';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

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

type ScheduleCreationFeedback =
  | {
      status: 'pending';
      title: string;
      cadenceLabel: string;
    }
  | {
      status: 'success';
      schedule: AgentRunSchedule;
    };

const DAYS = [
  ['SUN', 'Sunday'],
  ['MON', 'Monday'],
  ['TUE', 'Tuesday'],
  ['WED', 'Wednesday'],
  ['THU', 'Thursday'],
  ['FRI', 'Friday'],
  ['SAT', 'Saturday'],
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

const DEFAULT_UPCOMING_RUN_LIMIT = 10;
const DEFAULT_UPCOMING_RUNS_PER_SCHEDULE = 3;
const TIME_OPTIONS = Array.from({ length: 24 * 4 }, (_, index) => {
  const hour = Math.floor(index / 4);
  const minute = (index % 4) * 15;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
});

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

function getUpcomingRuns(schedule: AgentRunSchedule) {
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

  return Array.from(runsByTime.values()).sort(
    (a, b) => a.runTime.getTime() - b.runTime.getTime()
  );
}

function isSchedulePaused(schedule: AgentRunSchedule) {
  return schedule.state === 'PAUSED' || schedule.paused;
}

function getScheduleTitle(schedule: AgentRunSchedule) {
  return schedule.name;
}

function describeRunCount(count: number) {
  if (count === 0) return 'Never run';
  return count === 1 ? '1 run' : `${count} runs`;
}

function formatTimezone(timezone: string) {
  return timezone.replaceAll('_', ' ');
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

function formatTimeValue(value: string) {
  const [hourText = '0', minute = '00'] = value.split(':');
  const hour = Number.parseInt(hourText, 10);
  return `${hour % 12 || 12}:${minute} ${hour >= 12 ? 'PM' : 'AM'}`;
}

function formatRunDateTime(date: Date) {
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function describeCadenceConfig(cadence: CadenceConfig) {
  if (cadence.type === 'interval') {
    return `Every ${cadence.intervalValue} ${cadence.intervalUnit}`;
  }
  const time = new Date(`2000-01-01T${cadence.time}:00`).toLocaleTimeString(
    undefined,
    {
      hour: 'numeric',
      minute: '2-digit',
    }
  );
  if (cadence.type === 'weekly') {
    const selectedDays = cadence.dayOfWeek.split(',');
    const isWeekdays =
      selectedDays.length === 5 &&
      ['MON', 'TUE', 'WED', 'THU', 'FRI'].every(day =>
        selectedDays.includes(day)
      );
    if (isWeekdays) return `Weekdays at ${time}`;
    const dayLabels = selectedDays.map(
      day => DAYS.find(([value]) => value === day)?.[1] ?? day
    );
    return `${dayLabels.join(', ')} at ${time}`;
  }
  if (cadence.type === 'monthly') {
    return `Monthly on day ${cadence.dayOfMonth} at ${time}`;
  }
  return `Daily at ${time}`;
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

function collectUpcomingRuns(items: ScheduleListItem[]) {
  return items
    .flatMap(item =>
      getUpcomingRuns(item.schedule).map(run => ({ ...item, ...run }))
    )
    .sort((a, b) => a.runTime.getTime() - b.runTime.getTime());
}

function getDefaultUpcomingRuns(items: UpcomingRunItem[]) {
  const countsBySchedule = new Map<string, number>();
  const visibleRuns: UpcomingRunItem[] = [];

  for (const item of items) {
    const count = countsBySchedule.get(item.schedule.id) ?? 0;
    if (count >= DEFAULT_UPCOMING_RUNS_PER_SCHEDULE) continue;
    visibleRuns.push(item);
    countsBySchedule.set(item.schedule.id, count + 1);
    if (visibleRuns.length >= DEFAULT_UPCOMING_RUN_LIMIT) break;
  }

  return visibleRuns;
}

function groupUpcomingRuns(items: UpcomingRunItem[]) {
  const groups = new Map<string, UpcomingRunItem[]>();
  for (const item of items) {
    const group = getUpcomingGroup(item.runTime);
    groups.set(group, [...(groups.get(group) ?? []), item]);
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
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(
          '[data-radix-popper-content-wrapper], [role="listbox"], [role="option"]'
        )
      ) {
        return;
      }
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
  const [creationFeedback, setCreationFeedback] =
    useState<ScheduleCreationFeedback | null>(null);
  const [editingSchedule, setEditingSchedule] =
    useState<AgentRunSchedule | null>(null);
  const dismissCreationFeedback = useCallback(
    () => setCreationFeedback(null),
    []
  );
  const createSchedule = useCreateAgentRunSchedule({
    agentexClient,
    agentId,
  });

  const handleCreate = async () => {
    const submittedPrompt = prompt.trim();
    if (!submittedPrompt) {
      toast.error('Enter a prompt to schedule');
      return;
    }
    const name = generateScheduleName(submittedPrompt, schedules);
    setCreationFeedback({
      status: 'pending',
      title: name,
      cadenceLabel: `${describeCadenceConfig(cadence)} · ${formatTimezone(timezone)}`,
    });
    setPrompt('');
    try {
      const schedule = await createSchedule.mutateAsync({
        name,
        timezone,
        ...cadenceToPayload(cadence),
        initial_input: {
          type: 'text',
          author: 'user',
          content: submittedPrompt,
        },
      });
      setCreationFeedback({ status: 'success', schedule });
    } catch {
      setCreationFeedback(null);
      setPrompt(currentPrompt => currentPrompt || submittedPrompt);
    }
  };

  return (
    <section className="mx-auto flex w-full max-w-4xl flex-col gap-3">
      <div className="border-input dark:bg-input flex flex-col gap-3 rounded-4xl border px-5 py-4 shadow-sm">
        <textarea
          value={prompt}
          onChange={event => setPrompt(event.target.value)}
          onKeyDown={event => {
            if (
              event.key === 'Enter' &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              if (!createSchedule.isPending) {
                void handleCreate();
              }
            }
          }}
          placeholder="What should this agent do on a schedule?"
          className="min-h-20 resize-none border-0 bg-transparent text-sm leading-6 outline-none focus:border-0 focus:ring-0 focus:outline-none focus-visible:outline-none"
        />
        <div className="flex flex-wrap items-center gap-3">
          <CadencePicker
            cadence={cadence}
            onChange={setCadence}
            timezone={timezone}
            onTimezoneChange={setTimezone}
          />
          <Button
            onClick={() => void handleCreate()}
            disabled={!prompt.trim() || createSchedule.isPending}
            className="ml-auto rounded-full"
          >
            {createSchedule.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ArrowUp className="size-4" />
            )}
            Schedule
          </Button>
        </div>
      </div>
      <p className="text-muted-foreground px-4 text-xs">
        Press Enter to schedule. Use Shift + Enter for a new line. You can edit
        the schedule afterward.
      </p>
      <ScheduleCreationStatus
        feedback={creationFeedback}
        onDismiss={dismissCreationFeedback}
        onEdit={schedule => setEditingSchedule(schedule)}
      />
      {editingSchedule && (
        <EditScheduleModal
          agentId={agentId}
          agentexClient={agentexClient}
          schedule={editingSchedule}
          onClose={() => setEditingSchedule(null)}
        />
      )}
    </section>
  );
}

function ScheduleCreationStatus({
  feedback,
  onDismiss,
  onEdit,
}: {
  feedback: ScheduleCreationFeedback | null;
  onDismiss: () => void;
  onEdit: (schedule: AgentRunSchedule) => void;
}) {
  const reduceMotion = useReducedMotion();
  const nextRun =
    feedback?.status === 'success' ? getNextRun(feedback.schedule) : null;

  useEffect(() => {
    if (feedback?.status !== 'success') return;
    const timeout = window.setTimeout(onDismiss, 10000);
    return () => window.clearTimeout(timeout);
  }, [feedback, onDismiss]);

  return (
    <AnimatePresence mode="wait">
      {feedback && (
        <motion.div
          key={feedback.status}
          initial={reduceMotion ? false : { opacity: 0, y: -8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          {...(reduceMotion
            ? {}
            : { exit: { opacity: 0, y: -4, scale: 0.99 } })}
          transition={{ duration: reduceMotion ? 0 : 0.2, ease: 'easeOut' }}
          className={cn(
            'border-border bg-card flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-sm',
            feedback.status === 'success' &&
              'border-emerald-500/30 bg-emerald-500/5'
          )}
          aria-live="polite"
        >
          {feedback.status === 'pending' ? (
            <motion.span
              className="size-2.5 shrink-0 rounded-full bg-[#7C5CFF]"
              animate={
                reduceMotion
                  ? false
                  : { scale: [1, 1.35, 1], opacity: [0.7, 1, 0.7] }
              }
              transition={{
                duration: 1.2,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
            />
          ) : (
            <CheckCircle2 className="size-5 shrink-0 text-emerald-600" />
          )}
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">
              {feedback.status === 'pending'
                ? `Scheduling “${feedback.title}”…`
                : `Scheduled “${getScheduleTitle(feedback.schedule)}”`}
            </div>
            <div className="text-muted-foreground truncate text-xs">
              {feedback.status === 'pending'
                ? feedback.cadenceLabel
                : nextRun
                  ? `Next run ${formatUpcomingSubtitle(nextRun)}`
                  : 'Schedule created successfully'}
            </div>
          </div>
          {feedback.status === 'success' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                onEdit(feedback.schedule);
                onDismiss();
              }}
            >
              <Pencil className="size-3.5" />
              Edit
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={onDismiss}
            aria-label="Dismiss schedule status"
          >
            <X className="size-4" />
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function CadencePicker({
  cadence,
  onChange,
  timezone,
  onTimezoneChange,
  expanded = false,
}: {
  cadence: CadenceConfig;
  onChange: (cadence: CadenceConfig) => void;
  timezone: string;
  onTimezoneChange: (timezone: string) => void;
  expanded?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const pickerRef = useCloseOnOutsideClick<HTMLDivElement>(
    !expanded && isOpen,
    () => setIsOpen(false)
  );
  const setField = <K extends keyof CadenceConfig>(
    key: K,
    value: CadenceConfig[K]
  ) => onChange({ ...cadence, [key]: value });
  const selectedDays = cadence.dayOfWeek.split(',').filter(Boolean);
  const summary = describeCadenceConfig(cadence);

  const toggleDay = (day: string) => {
    const nextDays = selectedDays.includes(day)
      ? selectedDays.filter(selectedDay => selectedDay !== day)
      : [...selectedDays, day];
    if (nextDays.length === 0) return;
    const orderedDays = DAYS.map(([value]) => value).filter(value =>
      nextDays.includes(value)
    );
    setField('dayOfWeek', orderedDays.join(','));
  };

  return (
    <div ref={pickerRef} className="relative">
      {!expanded && (
        <Button
          type="button"
          variant="outline"
          className="rounded-full"
          onClick={() => setIsOpen(current => !current)}
          aria-expanded={isOpen}
        >
          <Clock3 className="size-4" />
          {summary}
        </Button>
      )}
      {(expanded || isOpen) && (
        <div
          className={cn(
            'bg-popover text-popover-foreground rounded-2xl border p-4',
            expanded
              ? 'relative w-full shadow-sm'
              : 'absolute top-11 left-0 z-50 w-[min(30rem,calc(100vw-2rem))] shadow-xl'
          )}
        >
          <div className="text-muted-foreground mb-3 text-xs font-semibold tracking-wide uppercase">
            Cadence
          </div>
          <div className="bg-muted grid grid-cols-4 rounded-xl p-1">
            {(['daily', 'weekly', 'monthly', 'interval'] as const).map(type => (
              <button
                key={type}
                type="button"
                onClick={() => setField('type', type as CadenceType)}
                className={cn(
                  'rounded-lg px-3 py-2 text-sm font-medium capitalize transition-colors',
                  cadence.type === type
                    ? 'bg-white text-[#5B3FFF] shadow-sm dark:bg-slate-800 dark:text-[#A78BFA]'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {type}
              </button>
            ))}
          </div>

          <div className="mt-4 flex flex-col gap-4">
            {cadence.type === 'weekly' && (
              <div className="flex items-center justify-between gap-2">
                {DAYS.map(([value, label]) => {
                  const selected = selectedDays.includes(value);
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => toggleDay(value)}
                      className={cn(
                        'flex size-10 items-center justify-center rounded-full border text-sm font-semibold transition-colors',
                        selected
                          ? 'border-[#6F4DFF] bg-[#6F4DFF] text-white'
                          : 'border-input text-muted-foreground hover:border-[#6F4DFF]/50'
                      )}
                      aria-label={label}
                      aria-pressed={selected}
                    >
                      {label.charAt(0)}
                    </button>
                  );
                })}
              </div>
            )}

            {cadence.type === 'monthly' && (
              <div className="flex items-center gap-3">
                <span className="text-muted-foreground text-sm font-medium">
                  Day
                </span>
                <input
                  value={cadence.dayOfMonth}
                  onChange={event => setField('dayOfMonth', event.target.value)}
                  className="border-input bg-background h-10 w-20 rounded-xl border px-3 text-sm"
                  aria-label="Day of month"
                  inputMode="numeric"
                />
              </div>
            )}

            {cadence.type === 'interval' ? (
              <div className="flex items-center gap-3">
                <span className="text-muted-foreground text-sm font-medium">
                  Every
                </span>
                <input
                  value={cadence.intervalValue}
                  onChange={event =>
                    setField('intervalValue', event.target.value)
                  }
                  className="border-input bg-background h-10 w-20 rounded-xl border px-3 text-sm"
                  aria-label="Interval value"
                  inputMode="numeric"
                />
                <Select
                  value={cadence.intervalUnit}
                  onValueChange={value =>
                    setField(
                      'intervalUnit',
                      value as CadenceConfig['intervalUnit']
                    )
                  }
                >
                  <SelectTrigger className="min-w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="minutes">Minutes</SelectItem>
                    <SelectItem value="hours">Hours</SelectItem>
                    <SelectItem value="days">Days</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <TimePicker
                value={cadence.time}
                onChange={value => setField('time', value)}
              />
            )}

            <div className="flex items-center gap-3">
              <span className="text-muted-foreground text-sm font-medium">
                Timezone
              </span>
              <TimezoneSelect timezone={timezone} onChange={onTimezoneChange} />
            </div>
          </div>

          <div className="border-border text-muted-foreground mt-4 border-t pt-3 text-sm">
            Runs {summary.charAt(0).toLowerCase()}
            {summary.slice(1)}
          </div>
        </div>
      )}
    </div>
  );
}

function TimePicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const options = useMemo(
    () => Array.from(new Set([...TIME_OPTIONS, value])).sort(),
    [value]
  );

  return (
    <div className="flex items-center gap-3">
      <span className="text-muted-foreground text-sm font-medium">Time</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger
          className="h-10 min-w-40 rounded-xl px-4"
          aria-label="Schedule time"
        >
          <SelectValue>{formatTimeValue(value)}</SelectValue>
        </SelectTrigger>
        <SelectContent className="max-h-72">
          {options.map(option => (
            <SelectItem key={option} value={option}>
              {formatTimeValue(option)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
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
  const [showAll, setShowAll] = useState(false);
  const allRuns = useMemo(() => collectUpcomingRuns(items), [items]);
  const defaultRuns = useMemo(() => getDefaultUpcomingRuns(allRuns), [allRuns]);
  const visibleRuns = showAll ? allRuns : defaultRuns;
  const groupedItems = groupUpcomingRuns(visibleRuns);
  const hasMore = allRuns.length > defaultRuns.length;

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
      {hasMore && (
        <div className="text-muted-foreground mt-6 flex flex-wrap items-center justify-between gap-3 text-xs">
          <span>
            {showAll
              ? `Showing all ${allRuns.length} available upcoming runs · maximum 10 per schedule`
              : `Showing ${visibleRuns.length} of ${allRuns.length} upcoming runs · up to ${DEFAULT_UPCOMING_RUNS_PER_SCHEDULE} per schedule`}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full"
            onClick={() => setShowAll(current => !current)}
          >
            {showAll ? (
              <ChevronUp className="size-4" />
            ) : (
              <ChevronDown className="size-4" />
            )}
            {showAll ? 'Show fewer' : 'View more upcoming runs'}
          </Button>
        </div>
      )}
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
  const [isEditing, setIsEditing] = useState(false);
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
    <>
      <div className="relative flex items-center justify-between gap-4">
        <span className="absolute top-2 -left-8 z-10 size-2 rounded-full bg-[#7C5CFF]" />
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">
            {getScheduleTitle(schedule)}
          </div>
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
            onEdit={() => setIsEditing(true)}
            showScheduleActions={false}
            scheduledTime={item.runTime.toISOString()}
            isSkipped={item.isSkipped}
          />
        </div>
      </div>
      {isEditing && (
        <EditScheduleModal
          agentId={agentId}
          agentexClient={agentexClient}
          schedule={schedule}
          onClose={() => setIsEditing(false)}
        />
      )}
    </>
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
        <div className="truncate text-sm font-semibold">
          {getScheduleTitle(schedule)}
        </div>
        <div className="text-muted-foreground truncate text-sm">
          {describeCadence(schedule)}
          {` · ${formatTimezone(schedule.timezone)}`}
          {showAgentName ? ` · ${agentName}` : ''}
          {` · ${describeRunCount(schedule.num_actions_taken)}`}
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
          showScheduleActions={true}
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
  showScheduleActions,
  scheduledTime,
  isSkipped = false,
}: {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean | ((isOpen: boolean) => boolean)) => void;
  schedule: AgentRunSchedule;
  agentexClient: AgentexSDK;
  agentId: string;
  onEdit?: () => void;
  showScheduleActions: boolean;
  scheduledTime?: string;
  isSkipped?: boolean;
}) {
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
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
  const isPaused = isSchedulePaused(schedule);
  const canSkip = scheduledTime != null && !isPaused;

  return (
    <>
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
            {showScheduleActions && (
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
                {showScheduleActions ? 'Skip next run' : 'Skip run'}
              </MenuButton>
            )}
            {showScheduleActions && (
              <MenuButton disabled title="Backend support needed">
                <Clock3 className="size-4" />
                Snooze
              </MenuButton>
            )}
            {showScheduleActions && (
              <>
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
                    setIsDeleteConfirmOpen(true);
                  }}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="size-4" />
                  Delete
                </MenuButton>
              </>
            )}
            {!showScheduleActions && onEdit && (
              <MenuButton
                onClick={() => {
                  setIsOpen(false);
                  onEdit();
                }}
              >
                <Pencil className="size-4" />
                Edit schedule
              </MenuButton>
            )}
          </div>
        )}
      </div>
      {isDeleteConfirmOpen && (
        <DeleteScheduleModal
          agentId={agentId}
          agentexClient={agentexClient}
          schedule={schedule}
          onClose={() => setIsDeleteConfirmOpen(false)}
        />
      )}
    </>
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

function DeleteScheduleModal({
  agentId,
  agentexClient,
  schedule,
  onClose,
  onDeleted,
}: {
  agentId: string;
  agentexClient: AgentexSDK;
  schedule: AgentRunSchedule;
  onClose: () => void;
  onDeleted?: () => void;
}) {
  const deleteSchedule = useScheduleAction({
    agentexClient,
    agentId,
    action: 'delete',
  });

  return (
    <BasicModal
      title="Delete schedule?"
      onClose={() => {
        if (!deleteSchedule.isPending) onClose();
      }}
    >
      <p className="text-muted-foreground text-sm leading-6">
        Deleting <span className="font-medium">{schedule.name}</span>{' '}
        permanently stops its future runs. Existing tasks are kept. This action
        cannot be undone.
      </p>
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          onClick={onClose}
          disabled={deleteSchedule.isPending}
        >
          Cancel
        </Button>
        <Button
          variant="destructive"
          disabled={deleteSchedule.isPending}
          onClick={() => {
            void deleteSchedule
              .mutateAsync(schedule.id)
              .then(() => {
                onClose();
                onDeleted?.();
              })
              .catch(() => undefined);
          }}
        >
          {deleteSchedule.isPending && (
            <Loader2 className="size-4 animate-spin" />
          )}
          Delete schedule
        </Button>
      </div>
    </BasicModal>
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
  const [isActive, setIsActive] = useState(!isSchedulePaused(schedule));
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const updateSchedule = useUpdateAgentRunSchedule({
    agentexClient,
    agentId,
  });

  const handleSave = async () => {
    const normalizedName = normalizeScheduleName(name);
    await updateSchedule.mutateAsync({
      scheduleId: schedule.id,
      payload: {
        name: normalizedName,
        timezone,
        paused: !isActive,
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
    <>
      <BasicModal title="Edit scheduled task" onClose={onClose}>
        <ScheduleNameInput name={name} setName={setName} />
        <textarea
          value={prompt}
          onChange={event => setPrompt(event.target.value)}
          className="border-input bg-background min-h-24 rounded-md border p-3 text-sm"
        />
        <CadencePicker
          cadence={cadence}
          onChange={setCadence}
          timezone={timezone}
          onTimezoneChange={setTimezone}
          expanded
        />
        <div className="border-border flex items-center justify-between rounded-xl border px-3 py-2.5">
          <div>
            <div className="text-sm font-medium">Schedule active</div>
            <div className="text-muted-foreground text-xs">
              Paused schedules do not create new runs.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIsActive(current => !current)}
            className={cn(
              'flex h-6 w-11 items-center rounded-full p-0.5 transition-colors',
              isActive ? 'bg-[#6F4DFF]' : 'bg-slate-200 dark:bg-slate-700'
            )}
            aria-label={isActive ? 'Pause schedule' : 'Activate schedule'}
            aria-pressed={isActive}
          >
            <span
              className={cn(
                'bg-background size-5 rounded-full shadow-sm transition-transform',
                isActive ? 'translate-x-5' : 'translate-x-0'
              )}
            />
          </button>
        </div>
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={() => setIsDeleteConfirmOpen(true)}
          >
            <Trash2 className="size-4" />
            Delete schedule…
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={
                !normalizeScheduleName(name) ||
                !prompt.trim() ||
                updateSchedule.isPending
              }
            >
              {updateSchedule.isPending && (
                <Loader2 className="size-4 animate-spin" />
              )}
              Save changes
            </Button>
          </div>
        </div>
      </BasicModal>
      {isDeleteConfirmOpen && (
        <DeleteScheduleModal
          agentId={agentId}
          agentexClient={agentexClient}
          schedule={schedule}
          onClose={() => setIsDeleteConfirmOpen(false)}
          onDeleted={onClose}
        />
      )}
    </>
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
        onChange={event =>
          setName(sanitizeScheduleNameInput(event.target.value))
        }
        onBlur={() => setName(normalizeScheduleName(name))}
        maxLength={64}
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
