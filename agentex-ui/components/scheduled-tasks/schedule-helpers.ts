import { useEffect, useRef } from 'react';

import type { AgentRunSchedule } from '@/lib/agent-run-schedules';

export type ScheduleView = 'upcoming' | 'all';

export type ScheduleListItem = {
  agentId: string;
  agentName: string;
  schedule: AgentRunSchedule;
};

export type UpcomingRunItem = ScheduleListItem & {
  runTime: Date;
  isSkipped: boolean;
};

const DEFAULT_UPCOMING_RUN_LIMIT = 10;
export const DEFAULT_UPCOMING_RUNS_PER_SCHEDULE = 3;

export function getBrowserTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

export function getNextRun(schedule: AgentRunSchedule) {
  const nextRun = schedule.next_action_times[0];
  return nextRun ? new Date(nextRun) : null;
}

export function getNextRunTime(schedule: AgentRunSchedule) {
  return getNextRun(schedule)?.getTime() ?? null;
}

export function getUpcomingRuns(schedule: AgentRunSchedule) {
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

export function isSchedulePaused(schedule: AgentRunSchedule) {
  return schedule.state === 'PAUSED' || schedule.paused;
}

export function describeRunCount(count: number) {
  if (count === 0) return '0 runs';
  return count === 1 ? '1 run' : `${count} runs`;
}

export function formatTimezone(timezone: string) {
  return timezone.replaceAll('_', ' ');
}

export function sortScheduleItems(
  items: ScheduleListItem[],
  view: ScheduleView
) {
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

export function getUpcomingGroup(date: Date) {
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

export function formatUpcomingSubtitle(date: Date) {
  const group = getUpcomingGroup(date);
  if (group === 'Today') {
    return `Today, ${formatRunTime(date)}`;
  }
  if (group === 'Tomorrow') {
    return `Tomorrow, ${formatRunTime(date)}`;
  }
  return formatRunDateTime(date);
}

export function collectUpcomingRuns(items: ScheduleListItem[]) {
  return items
    .flatMap(item =>
      getUpcomingRuns(item.schedule).map(run => ({ ...item, ...run }))
    )
    .sort((a, b) => a.runTime.getTime() - b.runTime.getTime());
}

export function getDefaultUpcomingRuns(items: UpcomingRunItem[]) {
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

export function groupUpcomingRuns(items: UpcomingRunItem[]) {
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

export function useCloseOnOutsideClick<T extends HTMLElement>(
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
