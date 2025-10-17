import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { Code } from "@/registry/agentex/code/code";
import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from "agentex/resources";
import { cva } from "class-variance-authority";
import { ChevronsUpDown } from "lucide-react";
import { memo } from "react";

const variants = cva("rounded-md p-4 flex flex-col gap-2", {
  variants: {
    author: {
      user: "bg-accent text-accent-foreground",
      agent: "bg-background",
    },
  },
});

type TaskMessageToolPairComponentProps = {
  toolRequestMessage: TaskMessage & { content: ToolRequestContent };
  toolResponseMessage?:
    | (TaskMessage & { content: ToolResponseContent })
    | undefined;
  theme: "dark" | "light";
};

function TaskMessageToolPairComponent({
  toolRequestMessage,
  toolResponseMessage,
  theme,
}: TaskMessageToolPairComponentProps) {
  return (
    <Collapsible
      className={cn(variants({ author: toolRequestMessage.content.author }))}
    >
      <div>
        <CollapsibleTrigger className="flex items-center">
          <span className="px-4 py-2 font-mono">
            {toolRequestMessage.content.name}
          </span>
          <span className="cursor-pointer size-8 m-2 inline-flex items-center justify-center">
            <ChevronsUpDown />
            <span className="sr-only">Details</span>
          </span>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent className="flex flex-col ml-8 gap-4">
        <div className="group">
          <blockquote>Request</blockquote>
          <Code
            agentexWhitespaceWrap
            agentexCodeLanguage="json"
            agentexColorTheme={theme}
            className="overflow-x-auto max-w-full"
          >
            {JSON.stringify(toolRequestMessage.content.arguments, null, 2)}
          </Code>
        </div>

        <div className="group">
          <blockquote>Response</blockquote>
          {toolResponseMessage === undefined ? (
            <code>pending...</code>
          ) : (
            <Code
              agentexWhitespaceWrap
              agentexCodeLanguage="json"
              agentexColorTheme={theme}
              className="overflow-x-auto max-w-full"
            >
              {typeof toolResponseMessage.content.content === "string"
                ? toolResponseMessage.content.content
                : JSON.stringify(toolResponseMessage.content.content, null, 2)}
            </Code>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

const MemoizedTaskMessageToolPairComponent = memo(TaskMessageToolPairComponent);

export { MemoizedTaskMessageToolPairComponent, TaskMessageToolPairComponent };

