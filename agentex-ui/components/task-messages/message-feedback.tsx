'use client';

import { useCallback, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { Loader2, ThumbsDown, ThumbsUp } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { IconButton } from '@/components/ui/icon-button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useFeedback } from '@/hooks/use-feedback';
import { cn } from '@/lib/utils';

type MessageFeedbackProps = {
  messageId: string;
  taskId: string;
  agentMessageContent: string;
  userMessageContent: string;
};

export function MessageFeedback({
  messageId,
  taskId,
  agentMessageContent,
  userMessageContent,
}: MessageFeedbackProps) {
  const [selection, setSelection] = useState<'approved' | 'rejected' | null>(
    null
  );
  const [showCommentForm, setShowCommentForm] = useState(false);
  const [comment, setComment] = useState('');

  const { mutateAsync, isPending } = useFeedback();

  const submitFeedback = useCallback(
    async (approval: 'approved' | 'rejected', feedbackComment?: string) => {
      try {
        await mutateAsync({
          traceId: taskId,
          messageId,
          taskId,
          input: userMessageContent,
          output: agentMessageContent,
          approval,
          ...(feedbackComment ? { comment: feedbackComment } : {}),
        });
        setSelection(approval);
        setShowCommentForm(false);
        setComment('');
      } catch {
        // Error handled by the hook's onError
      }
    },
    [mutateAsync, taskId, messageId, userMessageContent, agentMessageContent]
  );

  const handleThumbsUp = useCallback(() => {
    if (isPending || selection === 'approved') return;
    submitFeedback('approved');
  }, [isPending, selection, submitFeedback]);

  const handleThumbsDown = useCallback(() => {
    if (isPending || selection === 'rejected') return;
    setShowCommentForm(prev => !prev);
  }, [isPending, selection]);

  const handleCommentSubmit = useCallback(() => {
    submitFeedback('rejected', comment || undefined);
  }, [submitFeedback, comment]);

  const handleCommentCancel = useCallback(() => {
    setShowCommentForm(false);
    setComment('');
  }, []);

  const isThumbsUpActive = selection === 'approved';
  const isThumbsDownActive = selection === 'rejected';

  return (
    <div className="flex flex-col gap-2">
      <div
        className={cn(
          'flex items-center gap-1 transition-opacity duration-200',
          selection
            ? 'opacity-100'
            : 'opacity-0 group-hover/feedback:opacity-100'
        )}
      >
        <TooltipProvider delayDuration={100}>
          <Tooltip>
            <TooltipTrigger asChild>
              <IconButton
                icon={isPending && !isThumbsDownActive ? Loader2 : ThumbsUp}
                variant="ghost"
                iconSize="sm"
                onClick={handleThumbsUp}
                disabled={isPending || !!selection}
                className={cn(
                  'size-6 transition-colors',
                  isThumbsUpActive && 'text-green-600 dark:text-green-400',
                  isPending && !isThumbsDownActive && '[&_svg]:animate-spin'
                )}
                aria-label="Thumbs up"
              />
            </TooltipTrigger>
            <TooltipContent>
              <p>Good response</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider delayDuration={100}>
          <Tooltip>
            <TooltipTrigger asChild>
              <IconButton
                icon={isPending && isThumbsDownActive ? Loader2 : ThumbsDown}
                variant="ghost"
                iconSize="sm"
                onClick={handleThumbsDown}
                disabled={isPending || !!selection}
                className={cn(
                  'size-6 transition-colors',
                  isThumbsDownActive && 'text-red-500 dark:text-red-400',
                  isPending && isThumbsDownActive && '[&_svg]:animate-spin'
                )}
                aria-label="Thumbs down"
              />
            </TooltipTrigger>
            <TooltipContent>
              <p>Bad response</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <AnimatePresence>
        {showCommentForm && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-border bg-muted/50 flex flex-col gap-2 rounded-md border p-3">
              <textarea
                value={comment}
                onChange={e => setComment(e.target.value)}
                placeholder="What could be improved?"
                maxLength={300}
                rows={2}
                className="border-input bg-background placeholder:text-muted-foreground focus-visible:ring-ring w-full resize-none rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
              />
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={handleCommentSubmit}
                  disabled={isPending}
                >
                  {isPending ? 'Submitting...' : 'Submit'}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleCommentCancel}
                  disabled={isPending}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
