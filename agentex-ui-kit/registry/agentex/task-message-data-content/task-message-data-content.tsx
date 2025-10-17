import { cn } from "@/lib/utils";
import { Code } from "@/registry/agentex/code/code";
import type { DataContent } from "agentex/resources";
import { cva } from "class-variance-authority";

const variants = cva("rounded-md p-4", {
  variants: {
    author: {
      user: "bg-accent text-accent-foreground",
      agent: "bg-background",
    },
  },
});

type TaskMessageDataContentComponentProps = {
  content: DataContent;
  theme: 'dark' | 'light';
};

function TaskMessageDataContentComponent({
  content,
  theme,
}: TaskMessageDataContentComponentProps) {
  return (
    <div className={cn(variants({ author: content.author }))}>
      <Code agentexWhitespaceWrap agentexCodeLanguage="json" agentexColorTheme={theme}>
        {JSON.stringify(content.data, null, 2)}
      </Code>
    </div>
  );
}

export { TaskMessageDataContentComponent };
