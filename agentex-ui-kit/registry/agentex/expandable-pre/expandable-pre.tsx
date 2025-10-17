import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { cva } from "class-variance-authority";
import {
  memo,
  ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

const preVariants = cva(
  "text-neutral font-sans text-pretty whitespace-pre-wrap wrap-anywhere",
  {
    variants: {
      fontSize: {
        sm: "text-sm",
        md: "text-md",
      },
      fontWeight: {
        normal: "font-normal",
        semibold: "font-semibold",
      },
    },
    defaultVariants: {
      fontSize: "md",
      fontWeight: "normal",
    },
  }
);

const buttonVariants = cva("text-neutral", {
  variants: {
    fontSize: {
      sm: "text-sm",
      md: "text-md",
    },
    fontWeight: {
      normal: "font-normal",
      semibold: "font-semibold",
    },
  },
  defaultVariants: {
    fontSize: "md",
    fontWeight: "normal",
  },
});

type ExpandablePreProps = {
  children: ReactNode;
  isForceExpanded?: boolean;
  /**
   * must be an integer, at least 1
   */
  lineClampValue: number;

  /**
   * @default 'md'
   */
  fontSize?: "sm" | "md";

  /**
   * @default 'normal'
   */
  fontWeight?: "normal" | "semibold";
  className?: string;
};

function ExpandablePre({
  children,
  isForceExpanded,
  lineClampValue,
  fontSize,
  fontWeight,
  className,
}: ExpandablePreProps) {
  const [isSelfExpanded, setIsSelfExpanded] = useState(false);
  const isExpanded = isForceExpanded || isSelfExpanded;
  const [isClamped, setIsClamped] = useState(false);

  const responseRef = useRef<HTMLPreElement | null>(null);

  const updateClamped = useCallback(() => {
    if (isExpanded || !responseRef.current) {
      return;
    }
    setIsClamped(
      responseRef.current.scrollHeight > responseRef.current.clientHeight
    );
  }, [isExpanded, setIsClamped]);

  useEffect(() => {
    updateClamped();

    window.addEventListener("resize", updateClamped);

    return () => {
      window.removeEventListener("resize", updateClamped);
    };
  }, [updateClamped]);

  return (
    <div
      className={cn(
        "w-full flex flex-col gap-1 items-start",
        {
          "hover:bg-foreground/10": isClamped,
        },
        className
      )}
    >
      <pre
        className={preVariants({
          fontSize,
          fontWeight,
        })}
        style={
          isExpanded
            ? {}
            : {
                display: "-webkit-box",
                WebkitLineClamp: lineClampValue,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }
        }
        ref={(node) => {
          responseRef.current = node;
          updateClamped();
        }}
      >
        {children}
      </pre>
      {isClamped && !isForceExpanded && (
        <Button
          variant="link"
          className={buttonVariants({
            fontSize,
            fontWeight,
          })}
          onClick={(e) => {
            if (isClamped) {
              setIsSelfExpanded((prev) => !prev);
            }
            e.stopPropagation();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              if (isClamped) {
                setIsSelfExpanded((prev) => !prev);
              }
              e.stopPropagation();
            }
          }}
        >
          {isExpanded ? "Show less" : "Show more"}
        </Button>
      )}
    </div>
  );
}

const MemoizedExpandablePre = memo(ExpandablePre);

export { ExpandablePre, MemoizedExpandablePre };
