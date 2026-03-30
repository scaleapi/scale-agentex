import { useMutation } from '@tanstack/react-query';

import { toast } from '@/components/ui/toast';

type SubmitFeedbackParams = {
  traceId: string;
  messageId: string;
  taskId: string;
  input: string;
  output: string;
  approval: 'approved' | 'rejected';
  comment?: string;
};

type FeedbackResponse = {
  spanId: string;
  assessmentId: string;
};

export function useFeedback() {
  return useMutation({
    mutationFn: async (
      params: SubmitFeedbackParams
    ): Promise<FeedbackResponse> => {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          data.error ?? `Request failed with status ${response.status}`
        );
      }

      return response.json();
    },
    onSuccess: () => {
      toast.success('Feedback submitted');
    },
    onError: (error: Error) => {
      toast.error({
        title: 'Failed to submit feedback',
        message: error.message,
      });
    },
  });
}
