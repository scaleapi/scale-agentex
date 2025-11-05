'use client';

import { useEffect, useState } from 'react';

import { motion } from 'framer-motion';
import { useForm } from 'react-hook-form';

import { useAgentexClient } from '@/components/providers';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { ShimmeringText } from '@/components/ui/shimmering-text';
import { Textarea } from '@/components/ui/textarea';
import { useSendMessage } from '@/hooks/use-task-messages';

type HumanResponseFormValues = {
  response: string;
};

type HumanResponseFormProps = {
  message: string;
  taskId: string;
  agentName: string;
  userResponse?: string | null;
  isResponded?: boolean;
};

export function HumanResponseForm({
  message,
  taskId,
  agentName,
  userResponse = null,
  isResponded = false,
}: HumanResponseFormProps) {
  const { agentexClient } = useAgentexClient();
  const sendMessageMutation = useSendMessage({ agentexClient });

  // Track local submission state for optimistic UI
  const [localSubmittedResponse, setLocalSubmittedResponse] = useState<
    string | null
  >(null);

  // Determine the effective state (use local state if submitted, otherwise use props)
  const effectiveResponse = localSubmittedResponse || userResponse;
  const effectiveIsResponded = localSubmittedResponse !== null || isResponded;

  const form = useForm<HumanResponseFormValues>({
    defaultValues: {
      response: effectiveResponse || '',
    },
  });

  // Update form when response comes in from props or local state changes
  useEffect(() => {
    if (effectiveResponse) {
      form.setValue('response', effectiveResponse);
    }
  }, [effectiveResponse, form]);

  const handleSubmit = async (values: HumanResponseFormValues) => {
    try {
      // Optimistically set the local submitted response
      setLocalSubmittedResponse(values.response);

      await sendMessageMutation.mutateAsync({
        taskId,
        agentName,
        content: {
          type: 'text',
          author: 'user',
          format: 'plain',
          attachments: [],
          content: values.response,
        },
      });

      // Don't reset the form - keep the submitted value showing
    } catch (error) {
      console.error('Failed to send human response:', error);
      // On error, clear the optimistic state
      setLocalSubmittedResponse(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Command+Enter (Mac) or Ctrl+Enter (Windows/Linux)
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      form.handleSubmit(handleSubmit)();
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="border-border bg-card my-4 w-full rounded-lg border p-6 shadow-lg"
    >
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <ShimmeringText
            text={
              effectiveIsResponded
                ? 'Human response received'
                : 'Waiting for human response'
            }
            enabled={!effectiveIsResponded && !sendMessageMutation.isPending}
          />
        </div>

        {message && (
          <div className="text-muted-foreground bg-muted/50 rounded-md p-3 text-sm">
            {message}
          </div>
        )}

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            <FormField
              control={form.control}
              name="response"
              rules={
                !effectiveIsResponded
                  ? { required: 'Response is required' }
                  : {}
              }
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Your Response</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder="Enter your response"
                      rows={3}
                      className="resize-none"
                      disabled={
                        sendMessageMutation.isPending || effectiveIsResponded
                      }
                      readOnly={effectiveIsResponded}
                      onKeyDown={handleKeyDown}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {!effectiveIsResponded && (
              <Button
                type="submit"
                disabled={sendMessageMutation.isPending}
                className="w-full"
              >
                {sendMessageMutation.isPending ? 'Sending...' : 'Send Response'}
              </Button>
            )}
          </form>
        </Form>
      </div>
    </motion.div>
  );
}
