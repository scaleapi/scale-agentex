'use client';

import { useMemo, useState, type ReactNode } from 'react';

import { CalendarX2, ChevronDown, ChevronUp, Play, X } from 'lucide-react';

import { ScheduleOverflowMenu } from '@/components/scheduled-tasks/all-schedules-list';
import { EditScheduleModal } from '@/components/scheduled-tasks/schedule-modals';
import { Button } from '@/components/ui/button';
import { useScheduleAction } from '@/hooks/use-agent-run-schedules';
import type { AgentRunSchedule } from '@/lib/agent-run-schedules';

import {
  collectUpcomingRuns,
  DEFAULT_UPCOMING_RUNS_PER_SCHEDULE,
  formatUpcomingSubtitle,
  getDefaultUpcomingRuns,
  groupUpcomingRuns,
  type ScheduleListItem,
  type UpcomingRunItem,
} from './schedule-helpers';

import type AgentexSDK from 'agentex';

export function UpcomingScheduleList({
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
  const skip = useScheduleAction({ agentexClient, agentId, action: 'skip' });
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
            icon={<Play className="size-4" />}
            onClick={onRunNow}
            disabled={isRunNowPending}
          />
          <RunNowOption
            title="Run now & skip scheduled run"
            description={`Runs once right now and skips only the scheduled run at ${runLabel}. Future scheduled runs are unchanged.`}
            icon={<CalendarX2 className="size-4" />}
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
  icon,
  onClick,
  disabled,
}: {
  title: string;
  description: string;
  icon: ReactNode;
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
        {icon}
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
