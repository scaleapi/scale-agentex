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

export function sanitizeScheduleNameInput(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '')
    .replace(/^-+/g, '')
    .slice(0, 64);
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

export function getCadenceValidationError(
  cadence: CadenceConfig
): string | null {
  if (cadence.type === 'interval') {
    if (!/^\d+$/.test(cadence.intervalValue)) {
      return 'Enter a whole-number interval.';
    }
    const value = Number(cadence.intervalValue);
    if (!Number.isSafeInteger(value) || value < 1) {
      return 'Interval must be at least 1.';
    }
    return null;
  }

  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(cadence.time)) {
    return 'Select a valid time.';
  }

  if (cadence.type === 'weekly') {
    const validDays = new Set([
      'SUN',
      'MON',
      'TUE',
      'WED',
      'THU',
      'FRI',
      'SAT',
    ]);
    const days = cadence.dayOfWeek.split(',').filter(Boolean);
    if (days.length === 0 || days.some(day => !validDays.has(day))) {
      return 'Select at least one valid weekday.';
    }
  }

  if (cadence.type === 'monthly') {
    if (!/^\d+$/.test(cadence.dayOfMonth)) {
      return 'Enter a whole-number day of month.';
    }
    const day = Number(cadence.dayOfMonth);
    if (!Number.isInteger(day) || day < 1 || day > 31) {
      return 'Day of month must be between 1 and 31.';
    }
  }

  return null;
}

export function cadenceToPayload(
  cadence: CadenceConfig
):
  | { cron_expression: string; interval_seconds?: never }
  | { interval_seconds: number; cron_expression?: never } {
  const validationError = getCadenceValidationError(cadence);
  if (validationError) {
    throw new Error(validationError);
  }

  if (cadence.type === 'interval') {
    const value = Number(cadence.intervalValue);
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
    const day = Number(cadence.dayOfMonth);
    return { cron_expression: `${cronMinute} ${cronHour} ${day} * *` };
  }

  return { cron_expression: `${cronMinute} ${cronHour} * * *` };
}

export function describeCadence(schedule: AgentRunSchedule): string {
  if (schedule.interval_seconds != null) {
    if (schedule.interval_seconds % 86400 === 0) {
      const days = schedule.interval_seconds / 86400;
      return `Every ${days} ${days === 1 ? 'day' : 'days'}`;
    }
    if (schedule.interval_seconds % 3600 === 0) {
      const hours = schedule.interval_seconds / 3600;
      return `Every ${hours} ${hours === 1 ? 'hour' : 'hours'}`;
    }
    if (schedule.interval_seconds % 60 === 0) {
      const minutes = schedule.interval_seconds / 60;
      return `Every ${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`;
    }
    return `Every ${schedule.interval_seconds} ${
      schedule.interval_seconds === 1 ? 'second' : 'seconds'
    }`;
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] =
    schedule.cron_expression?.split(' ') ?? [];
  if (
    minute == null ||
    hour == null ||
    dayOfMonth == null ||
    month == null ||
    dayOfWeek == null ||
    !/^\d+$/.test(minute) ||
    !/^\d+$/.test(hour) ||
    month !== '*'
  ) {
    return schedule.cron_expression
      ? `Cron schedule (${schedule.cron_expression})`
      : 'No cadence';
  }

  const hourNumber = Number.parseInt(hour, 10);
  const minuteNumber = Number.parseInt(minute, 10);
  const period = hourNumber >= 12 ? 'PM' : 'AM';
  const displayHour = hourNumber % 12 || 12;
  const time = `${displayHour}:${String(minuteNumber).padStart(2, '0')} ${period}`;

  if (dayOfWeek !== '*') {
    const dayLabels: Record<string, string> = {
      MON: 'Monday',
      TUE: 'Tuesday',
      WED: 'Wednesday',
      THU: 'Thursday',
      FRI: 'Friday',
      SAT: 'Saturday',
      SUN: 'Sunday',
      'MON-FRI': 'weekday',
    };
    const days = dayOfWeek
      .split(',')
      .map(day => dayLabels[day] ?? day)
      .join(', ');
    return `Every ${days} at ${time}`;
  }

  if (dayOfMonth !== '*') {
    return `Monthly on day ${dayOfMonth} at ${time}`;
  }

  return `Daily at ${time}`;
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
