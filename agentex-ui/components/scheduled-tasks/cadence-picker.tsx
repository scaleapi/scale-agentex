'use client';

import { useMemo, useState } from 'react';

import { Clock3 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  describeCadenceConfig,
  getCadenceValidationError,
  type CadenceConfig,
  type CadenceType,
} from '@/lib/schedule-utils';
import { cn } from '@/lib/utils';

import { getBrowserTimezone, useCloseOnOutsideClick } from './schedule-helpers';

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

const TIME_OPTIONS = Array.from({ length: 24 * 4 }, (_, index) => {
  const hour = Math.floor(index / 4);
  const minute = (index % 4) * 15;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
});

function formatTimeValue(value: string) {
  const [hourText = '0', minute = '00'] = value.split(':');
  const hour = Number.parseInt(hourText, 10);
  return `${hour % 12 || 12}:${minute} ${hour >= 12 ? 'PM' : 'AM'}`;
}

export function CadencePicker({
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
  const validationError = getCadenceValidationError(cadence);

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

          <div
            className={cn(
              'border-border mt-4 border-t pt-3 text-sm',
              validationError ? 'text-destructive' : 'text-muted-foreground'
            )}
          >
            {validationError ? (
              validationError
            ) : (
              <>
                Runs {summary.charAt(0).toLowerCase()}
                {summary.slice(1)}
              </>
            )}
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
            {option.replaceAll('_', ' ')}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
