'use client';

import { useState, type ButtonHTMLAttributes } from 'react';

import {
  CalendarX2,
  Clock3,
  MoreHorizontal,
  PauseCircle,
  Pencil,
  Play,
  Trash2,
} from 'lucide-react';

import {
  DeleteScheduleModal,
  EditScheduleModal,
} from '@/components/scheduled-tasks/schedule-modals';
import { Button } from '@/components/ui/button';
import { useScheduleAction } from '@/hooks/use-agent-run-schedules';
import type { AgentRunSchedule } from '@/lib/agent-run-schedules';
import { describeCadence } from '@/lib/schedule-utils';
import { cn } from '@/lib/utils';

import {
  describeRunCount,
  formatTimezone,
  getNextRun,
  isSchedulePaused,
  type ScheduleListItem,
  useCloseOnOutsideClick,
} from './schedule-helpers';

import type AgentexSDK from 'agentex';

export function AllSchedulesList({
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

export function ScheduleOverflowMenu({
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
  const skip = useScheduleAction({ agentexClient, agentId, action: 'skip' });
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
                <CalendarX2 className="size-4" />
                {showScheduleActions ? 'Skip next run' : 'Skip run'}
              </MenuButton>
            )}
            {showScheduleActions && (
              <MenuButton disabled title="Snooze support is coming soon">
                <Clock3 className="size-4" />
                Snooze — coming soon
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
}: ButtonHTMLAttributes<HTMLButtonElement>) {
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
