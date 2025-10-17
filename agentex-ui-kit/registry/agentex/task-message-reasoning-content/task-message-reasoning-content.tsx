import { cn } from "@/lib/utils";
import { ExpandablePre } from "@/registry/agentex/expandable-pre/expandable-pre";
import type { ReasoningContent } from "agentex/resources";
import { cva } from "class-variance-authority";

const variants = cva("rounded-md p-4 flex flex-col gap-2", {
  variants: {
    author: {
      user: "bg-accent text-accent-foreground",
      agent: "bg-background",
    },
  },
});

type TaskMessageReasoningContentComponentProps = {
  content: ReasoningContent;
};

function TaskMessageReasoningContentComponent({
  content,
}: TaskMessageReasoningContentComponentProps) {
  return (
    <div className={cn(variants({ author: content.author }))}>
      <span className="font-mono">Reasoning</span>
      {content.summary.map((summary, index) => (
        <div
          key={index}
          className="flex flex-col gap-1 text-muted-foreground ml-2"
        >
          <div className="text-sm font-medium mb-1">{summary}</div>
          {content.content?.[index] && (
            <div className="pl-2 border-l">
              <ExpandablePre
                fontSize="sm"
                fontWeight="normal"
                lineClampValue={2}
              >
                {content.content[index]}
              </ExpandablePre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export { TaskMessageReasoningContentComponent };
