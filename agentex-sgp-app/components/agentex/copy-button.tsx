'use client';

import { Button } from '@/components/ui/button';
import { Copy, Check } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useState, useCallback, useRef } from 'react';

interface CopyButtonProps {
  tooltip?: string;
  onClick?: () => void;
  content?: string;
  className?: string;
}

export function CopyButton({
  tooltip,
  onClick,
  content,
  className,
}: CopyButtonProps) {
  const [isCopying, setIsCopying] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleCopy = useCallback(() => {
    // Clear any existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    if (content) {
      navigator.clipboard.writeText(content).then(
        () => {
          setIsCopying(true);
          timeoutRef.current = setTimeout(() => {
            setIsCopying(false);
          }, 4000);
        },
        (err) => {
          console.error('Failed to copy content:', err);
        }
      );
    } else if (onClick) {
      onClick();
      setIsCopying(true);
      timeoutRef.current = setTimeout(() => {
        setIsCopying(false);
      }, 4000);
    }
  }, [content, onClick]);

  const buttonContent = (
    <Button
      variant="ghost"
      size="icon"
      onClick={handleCopy}
      className={`h-6 w-6 hover:bg-muted hover:text-muted-foreground transition-colors ${className || ''}`}
    >
      {isCopying ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
    </Button>
  );

  if (isCopying || !tooltip) {
    return buttonContent;
  }

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>{buttonContent}</TooltipTrigger>
        <TooltipContent>
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
