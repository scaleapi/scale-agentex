import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from '@/components/ai-elements/reasoning';
import type { ReasoningContent as ReasoningContentType } from 'agentex/resources';

type TaskMessageReasoningContentComponentProps = {
  content: ReasoningContentType;
  isStreaming?: boolean;
};

function TaskMessageReasoningContentComponent({
  content,
  isStreaming = false,
}: TaskMessageReasoningContentComponentProps) {
  const reasoningText = [...(content.content ?? []), ...content.summary].join(
    '\n'
  );

  return (
    <Reasoning
      className="w-full"
      isStreaming={isStreaming}
      defaultOpen={isStreaming}
    >
      <ReasoningTrigger title="Reasoning" />
      <ReasoningContent>{reasoningText}</ReasoningContent>
    </Reasoning>
  );
}

export { TaskMessageReasoningContentComponent };
