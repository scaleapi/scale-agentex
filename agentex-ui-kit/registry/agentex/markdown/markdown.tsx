"use client";

import { cn } from "@/lib/utils";
import { MemoizedCode } from "@/registry/agentex/code/code";
import { lazy, Suspense } from "react";
import remarkGfm from "remark-gfm";

const ReactMarkdown = lazy(() => import("react-markdown"));

type MarkdownProps = {
  theme: "dark" | "light";
  children: string;
  wrap?: boolean;
};

function Markdown({ theme, children, wrap = false }: MarkdownProps) {
  return (
    <Suspense
      fallback={
        <pre
          className={cn({
            "font-sans text-pretty whitespace-pre-wrap wrap-anywhere": wrap,
          })}
        >
          {children}
        </pre>
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[]}
        components={{
          code({ ...props }) {
            const [, agentexCodeLanguage] =
              /language-(\w+)/.exec(props.className ?? "") ?? [];
            return (
              <MemoizedCode
                {...props}
                agentexColorTheme={theme}
                agentexCodeLanguage={agentexCodeLanguage}
                agentexWhitespaceWrap={wrap}
              />
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </Suspense>
  );
}

export { Markdown };
