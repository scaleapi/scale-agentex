'use client';

import { useCallback, useEffect, useState } from 'react';

import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ArrowUp, CheckCircle2, Loader2, Pencil, X } from 'lucide-react';

import { CadencePicker } from '@/components/scheduled-tasks/cadence-picker';
import { EditScheduleModal } from '@/components/scheduled-tasks/schedule-modals';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/toast';
import { useCreateAgentRunSchedule } from '@/hooks/use-agent-run-schedules';
import type { AgentRunSchedule } from '@/lib/agent-run-schedules';
import {
  cadenceToPayload,
  DEFAULT_CADENCE,
  describeCadenceConfig,
  generateScheduleName,
  getCadenceValidationError,
} from '@/lib/schedule-utils';
import { cn } from '@/lib/utils';

import {
  formatTimezone,
  formatUpcomingSubtitle,
  getBrowserTimezone,
  getNextRun,
} from './schedule-helpers';

import type AgentexSDK from 'agentex';

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

export function ScheduleComposer({
  agentId,
  agentexClient,
  schedules,
}: {
  agentId: string;
  agentexClient: AgentexSDK;
  schedules: AgentRunSchedule[];
}) {
  const [prompt, setPrompt] = useState('');
  const [cadence, setCadence] = useState(DEFAULT_CADENCE);
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
  const cadenceError = getCadenceValidationError(cadence);

  const handleCreate = async () => {
    const submittedPrompt = prompt.trim();
    if (!submittedPrompt) {
      toast.error('Enter a prompt to schedule');
      return;
    }
    if (cadenceError) {
      toast.error(cadenceError);
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
            disabled={
              !prompt.trim() || !!cadenceError || createSchedule.isPending
            }
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
                : `Scheduled “${feedback.schedule.name}”`}
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
