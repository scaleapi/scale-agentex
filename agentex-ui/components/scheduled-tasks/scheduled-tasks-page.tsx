'use client';

import { useMemo, useState } from 'react';

import { CalendarClock, Loader2, MoreHorizontal } from 'lucide-react';

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
  useAgentRunScheduleDetails,
  useAgentRunSchedules,
  useCreateAgentRunSchedule,
  useScheduleAction,
  useUpdateAgentRunSchedule,
} from '@/hooks/use-agent-run-schedules';
import { useAgents } from '@/hooks/use-agents';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
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

export function ScheduledTasksPage() {
  const { agentName } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();
  const agentexAPIBaseURL = '/api/agentex';
  const { data: agents = [] } = useAgents(agentexClient);
  const { data: agentByName } = useAgentByName(agentexClient, agentName);
  const selectedAgent =
    agents.find(agent => agent.name === agentName) ?? agentByName ?? null;
  const agentId = selectedAgent?.id ?? null;

  const schedulesQuery = useAgentRunSchedules(agentexAPIBaseURL, agentId);
  const schedules = schedulesQuery.data ?? [];
  const detailQueries = useAgentRunScheduleDetails(
    agentexAPIBaseURL,
    agentId,
    schedules
  );
  const schedulesWithLiveFields = schedules.map((schedule, index) => {
    const detail = detailQueries[index]?.data;
    return detail ?? schedule;
  });

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <div className="border-border flex items-center justify-between border-b px-8 py-5">
        <div>
          <h1 className="text-foreground text-xl font-semibold">
            Scheduled Tasks
          </h1>
          <p className="text-muted-foreground text-sm">
            {agentName
              ? `Run ${agentName} automatically on a cadence.`
              : 'Select an agent to schedule recurring tasks.'}
          </p>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-8 py-6">
        {!selectedAgent ? (
          <EmptyState message="Select an agent to create scheduled tasks." />
        ) : (
          <>
            <ScheduleComposer
              agentId={selectedAgent.id}
              baseURL={agentexAPIBaseURL}
              schedules={schedules}
            />
            <ScheduleList
              agentId={selectedAgent.id}
              baseURL={agentexAPIBaseURL}
              schedules={schedulesWithLiveFields}
              isLoading={schedulesQuery.isLoading}
              error={schedulesQuery.error}
            />
          </>
        )}
      </div>
    </div>
  );
}

function ScheduleComposer({
  agentId,
  baseURL,
  schedules,
}: {
  agentId: string;
  baseURL: string;
  schedules: AgentRunSchedule[];
}) {
  const [prompt, setPrompt] = useState('');
  const [cadence, setCadence] = useState<CadenceConfig>(DEFAULT_CADENCE);
  const [timezone, setTimezone] = useState(getBrowserTimezone);
  const [pendingName, setPendingName] = useState<string | null>(null);
  const createSchedule = useCreateAgentRunSchedule({ baseURL, agentId });

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
          className="min-h-20 resize-none bg-transparent text-sm leading-6 outline-none"
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
  agentId,
  baseURL,
  schedules,
  isLoading,
  error,
}: {
  agentId: string;
  baseURL: string;
  schedules: AgentRunSchedule[];
  isLoading: boolean;
  error: Error | null;
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

  if (schedules.length === 0) {
    return <EmptyState message="No scheduled tasks yet" />;
  }

  return (
    <section className="mx-auto grid w-full max-w-4xl gap-3">
      {schedules.map(schedule => (
        <ScheduleCard
          key={schedule.id}
          agentId={agentId}
          baseURL={baseURL}
          schedule={schedule}
        />
      ))}
    </section>
  );
}

function ScheduleCard({
  agentId,
  baseURL,
  schedule,
}: {
  agentId: string;
  baseURL: string;
  schedule: AgentRunSchedule;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const pause = useScheduleAction({ baseURL, agentId, action: 'pause' });
  const resume = useScheduleAction({ baseURL, agentId, action: 'resume' });
  const trigger = useScheduleAction({ baseURL, agentId, action: 'trigger' });
  const deleteSchedule = useScheduleAction({
    baseURL,
    agentId,
    action: 'delete',
  });
  const isPaused = schedule.state === 'PAUSED' || schedule.paused;
  const nextRun = schedule.next_action_times[0];

  return (
    <article className="border-border bg-card rounded-2xl border p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-sm font-semibold">{schedule.name}</h2>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-xs',
                isPaused
                  ? 'bg-muted text-muted-foreground'
                  : 'bg-green-500/10 text-green-700 dark:text-green-400'
              )}
            >
              {isPaused ? 'Paused' : 'Active'}
            </span>
          </div>
          <p className="text-muted-foreground mt-1 line-clamp-2 text-sm">
            {schedule.initial_input.content}
          </p>
          <p className="text-muted-foreground mt-2 text-xs">
            {describeCadence(schedule)} · {schedule.timezone}
            {nextRun ? ` · Next run ${new Date(nextRun).toLocaleString()}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => trigger.mutate(schedule.id)}
            disabled={trigger.isPending}
          >
            Run Now
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              isPaused ? resume.mutate(schedule.id) : pause.mutate(schedule.id)
            }
            disabled={pause.isPending || resume.isPending}
          >
            {isPaused ? 'Resume' : 'Pause'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsEditing(true)}
          >
            Edit
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => deleteSchedule.mutate(schedule.id)}
            disabled={deleteSchedule.isPending}
          >
            Delete
          </Button>
          <MoreHorizontal className="text-muted-foreground mt-1 size-4" />
        </div>
      </div>
      {isEditing && (
        <EditScheduleModal
          agentId={agentId}
          baseURL={baseURL}
          schedule={schedule}
          onClose={() => setIsEditing(false)}
        />
      )}
    </article>
  );
}

function EditScheduleModal({
  agentId,
  baseURL,
  schedule,
  onClose,
}: {
  agentId: string;
  baseURL: string;
  schedule: AgentRunSchedule;
  onClose: () => void;
}) {
  const [name, setName] = useState(schedule.name);
  const [prompt, setPrompt] = useState(schedule.initial_input.content);
  const [cadence, setCadence] = useState(() => scheduleToCadence(schedule));
  const [timezone, setTimezone] = useState(schedule.timezone);
  const updateSchedule = useUpdateAgentRunSchedule({ baseURL, agentId });

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
