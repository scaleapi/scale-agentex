import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { cva } from "class-variance-authority";
import { CheckIcon, CopyIcon } from "lucide-react";
import { Highlight, themes } from "prism-react-renderer";
import { JSX, memo, useCallback, useState } from "react";

const highlightCodeBlockVariants = cva(
  "my-2 p-2 rounded-md grid grid-cols-[max-content_1fr] gap-x-2 max-w-full min-h-14",
  {
    variants: {
      wrap: {
        true: "whitespace-pre-wrap wrap-anywhere",
        false: "overflow-x-auto",
      },
    },
  }
);

const defaultCodeBlockVariants = cva("rounded-md", {
  variants: {
    wrap: {
      true: "whitespace-pre-wrap wrap-anywhere",
      false: "overflow-x-auto",
    },
  },
});

function Code({
  children,
  agentexColorTheme,
  agentexCodeLanguage,
  agentexWhitespaceWrap,
  className,
  ...props
}: JSX.IntrinsicElements["code"] & {
  agentexColorTheme: "dark" | "light";
  agentexCodeLanguage?: string | undefined | null;
  agentexWhitespaceWrap?: boolean | undefined | null;
}) {
  const wrap: boolean = !!agentexWhitespaceWrap;
  const [showCopySuccess, setShowCopySuccess] = useState(false);

  const syntaxHighlightContent = String(children).replace(/\n$/, "");

  const handleCopy = useCallback<() => void>(() => {
    navigator.clipboard.writeText(syntaxHighlightContent).then(() => {
      setShowCopySuccess(true);
      setTimeout(() => setShowCopySuccess(false), 1_000);
    });
  }, [syntaxHighlightContent]);

  if (agentexCodeLanguage) {
    return (
      <div className={cn("relative", className)}>
        <Button
          className="absolute top-2 right-2 z-10"
          size="icon"
          variant="ghost"
          aria-label="Copy code"
          onClick={(event) => {
            event.stopPropagation();
            handleCopy();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.stopPropagation();
              handleCopy();
            }
          }}
        >
          {showCopySuccess ? <CheckIcon color="green" /> : <CopyIcon />}
        </Button>
        <Highlight
          code={syntaxHighlightContent}
          language={agentexCodeLanguage}
          theme={
            agentexColorTheme === "dark"
              ? themes.nightOwl
              : themes.nightOwlLight
          }
          {...props}
        >
          {({ style, tokens, getLineProps, getTokenProps }) => (
            <pre style={style} className={highlightCodeBlockVariants({ wrap })}>
              {tokens.flatMap((line, i) => {
                const { className: lineClassName, ...lineProps } = getLineProps(
                  {
                    line,
                  }
                );

                return [
                  <span
                    key={`line-${i}`}
                    className="select-none text-slate-400 w-fit"
                  >
                    {i + 1}
                  </span>,
                  <div
                    key={`content-${i}`}
                    className={cn({ "flex flex-wrap": wrap }, lineClassName)}
                    {...lineProps}
                  >
                    {line.map((token, key) => (
                      <span key={key} {...getTokenProps({ token })} />
                    ))}
                  </div>,
                ];
              })}
            </pre>
          )}
        </Highlight>
      </div>
    );
  }

  // inline or no language
  return (
    <code className={defaultCodeBlockVariants({ wrap, className })} {...props}>
      {children}
    </code>
  );
}

const MemoizedCode = memo(Code);

export { Code, MemoizedCode };
