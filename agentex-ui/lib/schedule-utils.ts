import type { AgentRunSchedule } from '@/lib/agent-run-schedules';

export type CadenceType = 'daily' | 'weekly' | 'monthly' | 'interval';

export type CadenceConfig = {
  type: CadenceType;
  time: string;
  dayOfWeek: string;
  dayOfMonth: string;
  intervalValue: string;
  intervalUnit: 'minutes' | 'hours' | 'days';
};

export const DEFAULT_CADENCE: CadenceConfig = {
  type: 'daily',
  time: '09:00',
  dayOfWeek: 'MON',
  dayOfMonth: '1',
  intervalValue: '1',
  intervalUnit: 'hours',
};

export function normalizeScheduleName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
    .replace(/-+$/g, '');
}

export function generateScheduleName(
  prompt: string,
  existingSchedules: Pick<AgentRunSchedule, 'name'>[]
): string {
  const existingNames = new Set(
    existingSchedules.map(schedule => schedule.name)
  );
  const words = prompt.trim().split(/\s+/).slice(0, 6).join(' ');
  const base = normalizeScheduleName(words) || 'scheduled-task';

  if (!existingNames.has(base)) {
    return base;
  }

  for (let suffix = 2; suffix < 100; suffix += 1) {
    const suffixText = `-${suffix}`;
    const candidate = `${base.slice(0, 64 - suffixText.length)}${suffixText}`;
    if (!existingNames.has(candidate)) {
      return candidate;
    }
  }

  return `${base.slice(0, 55)}-${Date.now().toString().slice(-8)}`;
}

export function cadenceToPayload(
  cadence: CadenceConfig
):
  | { cron_expression: string; interval_seconds?: never }
  | { interval_seconds: number; cron_expression?: never } {
  if (cadence.type === 'interval') {
    const value = Math.max(1, Number.parseInt(cadence.intervalValue, 10) || 1);
    const multiplier =
      cadence.intervalUnit === 'minutes'
        ? 60
        : cadence.intervalUnit === 'hours'
          ? 60 * 60
          : 24 * 60 * 60;
    return { interval_seconds: value * multiplier };
  }

  const [hour = '9', minute = '0'] = cadence.time.split(':');
  const cronMinute = Number.parseInt(minute, 10) || 0;
  const cronHour = Number.parseInt(hour, 10) || 0;

  if (cadence.type === 'weekly') {
    return {
      cron_expression: `${cronMinute} ${cronHour} * * ${cadence.dayOfWeek}`,
    };
  }

  if (cadence.type === 'monthly') {
    const day = Math.min(
      31,
      Math.max(1, Number.parseInt(cadence.dayOfMonth, 10) || 1)
    );
    return { cron_expression: `${cronMinute} ${cronHour} ${day} * *` };
  }

  return { cron_expression: `${cronMinute} ${cronHour} * * *` };
}

export function describeCadence(schedule: AgentRunSchedule): string {
  if (schedule.interval_seconds != null) {
    if (schedule.interval_seconds % 86400 === 0) {
      return `Every ${schedule.interval_seconds / 86400} day(s)`;
    }
    if (schedule.interval_seconds % 3600 === 0) {
      return `Every ${schedule.interval_seconds / 3600} hour(s)`;
    }
    if (schedule.interval_seconds % 60 === 0) {
      return `Every ${schedule.interval_seconds / 60} minute(s)`;
    }
    return `Every ${schedule.interval_seconds} second(s)`;
  }

  return schedule.cron_expression ?? 'No cadence';
}

export function scheduleToCadence(schedule: AgentRunSchedule): CadenceConfig {
  if (schedule.interval_seconds != null) {
    if (schedule.interval_seconds % 86400 === 0) {
      return {
        ...DEFAULT_CADENCE,
        type: 'interval',
        intervalValue: String(schedule.interval_seconds / 86400),
        intervalUnit: 'days',
      };
    }
    if (schedule.interval_seconds % 3600 === 0) {
      return {
        ...DEFAULT_CADENCE,
        type: 'interval',
        intervalValue: String(schedule.interval_seconds / 3600),
        intervalUnit: 'hours',
      };
    }
    return {
      ...DEFAULT_CADENCE,
      type: 'interval',
      intervalValue: String(
        Math.max(1, Math.floor(schedule.interval_seconds / 60))
      ),
      intervalUnit: 'minutes',
    };
  }

  const [minute, hour, dayOfMonth, , dayOfWeek] =
    schedule.cron_expression?.split(' ') ?? [];
  const time =
    hour != null && minute != null
      ? `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
      : DEFAULT_CADENCE.time;

  if (dayOfMonth != null && dayOfMonth !== '*') {
    return {
      ...DEFAULT_CADENCE,
      type: 'monthly',
      time,
      dayOfMonth,
    };
  }

  if (dayOfWeek != null && dayOfWeek !== '*') {
    return {
      ...DEFAULT_CADENCE,
      type: 'weekly',
      time,
      dayOfWeek,
    };
  }

  return {
    ...DEFAULT_CADENCE,
    type: 'daily',
    time,
  };
}
