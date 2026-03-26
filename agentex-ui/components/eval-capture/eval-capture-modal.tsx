'use client';

import { useCallback, useMemo, useState } from 'react';

import { X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { Textarea } from '@/components/ui/textarea';
import {
  type ConversationMessage,
  type EvalCase,
  saveEvalCase,
} from '@/lib/eval-storage';

import type { TaskMessage } from 'agentex/resources';

type EvalCaptureModalProps = {
  open: boolean;
  onClose: () => void;
  messages: TaskMessage[];
  taskId: string;
  agentName: string;
  agentId: string;
};

export function EvalCaptureModal({
  open,
  onClose,
  messages,
  taskId,
  agentName,
  agentId,
}: EvalCaptureModalProps) {
  const conversation = useMemo(
    () => messagesToConversation(messages),
    [messages]
  );

  // Extract input (all user messages) and actual output (last agent text)
  const { userInput, agentOutput } = useMemo(
    () => extractInputOutput(conversation),
    [conversation]
  );

  const [editExpectedOutput, setEditExpectedOutput] = useState('');
  const [editTags, setEditTags] = useState('');
  const [notes, setNotes] = useState('');

  // Pre-fill expected output with actual output when modal opens
  const handleOpen = useCallback(() => {
    setEditExpectedOutput(agentOutput);
    setEditTags('');
    setNotes('');
  }, [agentOutput]);

  // Reset + pre-fill when modal becomes visible
  useMemo(() => {
    if (open) handleOpen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);

  const handleSave = useCallback(() => {
    const evalId = `eval-${agentName}-${taskId.split('-')[0]}-${Date.now().toString(36)}`;

    const evalCase: EvalCase = {
      id: evalId,
      input: userInput,
      expected_output: editExpectedOutput,
      actual_output: agentOutput,
      conversation,
      tags: editTags
        .split(',')
        .map(t => t.trim())
        .filter(Boolean),
      source: 'ui_capture',
      captured_at: new Date().toISOString(),
      notes,
    };

    saveEvalCase(agentName, agentId, evalCase);
    handleClose();
  }, [
    agentName,
    agentId,
    taskId,
    userInput,
    editExpectedOutput,
    agentOutput,
    conversation,
    editTags,
    notes,
    handleClose,
  ]);

  return (
    <Modal open={open} onClose={handleClose}>
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-foreground text-lg font-semibold">
            Capture Eval
          </h2>
          <button
            onClick={handleClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="size-5" />
          </button>
        </div>

        <p className="text-muted-foreground text-sm">
          Edit the agent&apos;s output to what it <strong>should</strong> have
          said. This becomes the golden answer for this eval case.
        </p>

        <FieldGroup label="Input (what was sent to the agent)">
          <div className="bg-muted text-muted-foreground max-h-32 overflow-y-auto rounded-md p-3 text-sm whitespace-pre-wrap">
            {userInput || '(no user input found)'}
          </div>
        </FieldGroup>

        <FieldGroup label="Actual Output (what the agent said)">
          <div className="bg-muted text-muted-foreground max-h-40 overflow-y-auto rounded-md p-3 text-sm whitespace-pre-wrap">
            {agentOutput || '(no agent output found)'}
          </div>
        </FieldGroup>

        <FieldGroup label="Expected Output (edit to what it should have said)">
          <Textarea
            value={editExpectedOutput}
            onChange={e => setEditExpectedOutput(e.target.value)}
            rows={6}
            placeholder="Edit the agent's response to be correct..."
          />
        </FieldGroup>

        <FieldGroup label="Notes (optional — what was wrong?)">
          <Textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={2}
            placeholder="e.g., Progress takeaways didn't reflect that Part 1 was completed but Part 2 was not..."
          />
        </FieldGroup>

        <FieldGroup label="Tags (optional, comma-separated)">
          <div className="flex flex-col gap-2">
            <input
              type="text"
              value={editTags}
              onChange={e => setEditTags(e.target.value)}
              placeholder="e.g., scorecard, reasoning, regression"
              className="border-input text-foreground bg-background w-full rounded-md border px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[1px] focus-visible:ring-[#756BA2]"
            />
            {editTags.trim() && (
              <div className="flex flex-wrap gap-1">
                {editTags
                  .split(',')
                  .map(t => t.trim())
                  .filter(Boolean)
                  .map(tag => (
                    <Badge key={tag} variant="secondary">
                      {tag}
                    </Badge>
                  ))}
              </div>
            )}
          </div>
        </FieldGroup>

        <div className="flex justify-between gap-2 pt-2">
          <Button variant="ghost" onClick={handleClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!editExpectedOutput.trim()}>
            Save Eval Case
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function FieldGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-foreground text-sm font-medium">{label}</label>
      {children}
    </div>
  );
}

// --- Helpers ---

function messagesToConversation(
  messages: TaskMessage[]
): ConversationMessage[] {
  return messages
    .filter(m => m.content.type !== 'tool_response')
    .map(m => {
      const content = m.content;
      switch (content.type) {
        case 'text':
          return {
            role:
              content.author === 'user'
                ? ('user' as const)
                : ('assistant' as const),
            content: content.content,
          };
        case 'tool_request':
          return {
            role: 'assistant' as const,
            content: `[Tool call: ${content.name}]`,
            tool_calls: [{ name: content.name, arguments: content.arguments }],
          };
        case 'reasoning':
          return {
            role: 'assistant' as const,
            content: `[Reasoning: ${content.summary?.join(' ') ?? ''}]`,
          };
        case 'data':
          return {
            role: 'assistant' as const,
            content: JSON.stringify(content.data),
          };
        default:
          return {
            role: 'assistant' as const,
            content: '[unknown message type]',
          };
      }
    });
}

function extractInputOutput(conversation: ConversationMessage[]): {
  userInput: string;
  agentOutput: string;
} {
  // Input = all user messages joined
  const userMessages = conversation
    .filter(m => m.role === 'user')
    .map(m => m.content);
  const userInput = userMessages.join('\n\n');

  // Output = last agent text message (not tool calls or reasoning)
  const agentTextMessages = conversation.filter(
    m =>
      m.role === 'assistant' &&
      !m.content.startsWith('[Tool call:') &&
      !m.content.startsWith('[Reasoning:')
  );
  const lastAgentMessage = agentTextMessages[agentTextMessages.length - 1];
  const agentOutput = lastAgentMessage?.content ?? '';

  return { userInput, agentOutput };
}
