import { cn } from "@/lib/utils";
import { Code } from "@/registry/agentex/code/code";
import { Markdown } from "@/registry/agentex/markdown/markdown";
import type { TextContent } from "agentex/resources";
import { cva } from "class-variance-authority";

const variants = cva("rounded-md p-4", {
  variants: {
    author: {
      user: "bg-accent text-accent-foreground",
      agent: "bg-background",
    },
  },
});

type TaskMessageTextContentComponentProps = {
  content: TextContent;
  theme: "dark" | "light";
};

function TaskMessageTextContentComponent({
  content,
  theme,
}: TaskMessageTextContentComponentProps) {
  return (
    <div className={cn(variants({ author: content.author }))}>
      {content.format === "plain" ? (
        <pre className="whitespace-pre-wrap wrap-anywhere font-sans">
          {content.content}
        </pre>
      ) : content.format === "code" ? (
        <Code agentexColorTheme={theme}>{content.content}</Code>
      ) : (
        <Markdown wrap theme={theme}>
          {content.content}
        </Markdown>
      )}
    </div>
  );
}

export { TaskMessageTextContentComponent };
