import { useMutation } from '@tanstack/react-query';

import { toast } from '@/components/ui/toast';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';

type SubmitFeedbackParams = {
  traceId: string;
  messageId: string;
  taskId: string;
  input: string;
  output: string;
  approval: 'approved' | 'rejected';
  comment?: string;
  agentName?: string;
  agentId?: string;
  agentAcpType?: string;
};

type FeedbackResponse = {
  spanId: string;
  assessmentIds: string[];
};

export function useFeedback() {
  const { sgpAccountID } = useSafeSearchParams();
  return useMutation({
    mutationFn: async (
      params: SubmitFeedbackParams
    ): Promise<FeedbackResponse> => {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Selected account (same source as the SDK); the BFF forwards it.
          ...(sgpAccountID ? { 'x-selected-account-id': sgpAccountID } : {}),
        },
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
