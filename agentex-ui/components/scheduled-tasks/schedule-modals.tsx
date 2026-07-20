'use client';

import { useState, type ReactNode } from 'react';

import { Loader2, Trash2 } from 'lucide-react';

import { CadencePicker } from '@/components/scheduled-tasks/cadence-picker';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/toast';
import {
  useScheduleAction,
  useUpdateAgentRunSchedule,
} from '@/hooks/use-agent-run-schedules';
import type { AgentRunSchedule } from '@/lib/agent-run-schedules';
import {
  cadenceToPayload,
  getCadenceValidationError,
  normalizeScheduleName,
  sanitizeScheduleNameInput,
  scheduleToCadence,
} from '@/lib/schedule-utils';
import { cn } from '@/lib/utils';

import { isSchedulePaused } from './schedule-helpers';

import type AgentexSDK from 'agentex';

export function DeleteScheduleModal({
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

export function EditScheduleModal({
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
  const cadenceError = getCadenceValidationError(cadence);

  const handleSave = async () => {
    if (cadenceError) {
      toast.error(cadenceError);
      return;
    }
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
              onClick={() => {
                void handleSave().catch(() => undefined);
              }}
              disabled={
                !normalizeScheduleName(name) ||
                !prompt.trim() ||
                !!cadenceError ||
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
  children: ReactNode;
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
