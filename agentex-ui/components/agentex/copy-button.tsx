'use client';

import { useCallback, useRef, useState } from 'react';

import { Check, Copy } from 'lucide-react';

import { IconButton } from '@/components/agentex/icon-button';
import { toast } from '@/components/agentex/toast';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export interface CopyButtonProps {
  tooltip?: string;
  onClick?: () => void;
  content?: string;
  className?: string;
  timeout?: number;
}

export function CopyButton({
  tooltip,
  onClick,
  content,
  className,
  timeout = 4000,
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
          }, timeout);
        },
        err => {
          toast.error({
            title: 'Failed to copy content',
            message: err instanceof Error ? err.message : 'Please try again.',
          });
        }
      );
    } else if (onClick) {
      onClick();
      setIsCopying(true);
      timeoutRef.current = setTimeout(() => {
        setIsCopying(false);
      }, timeout);
    }
  }, [content, onClick, timeout]);

  const buttonContent = (
    <IconButton
      icon={isCopying ? Check : Copy}
      variant="ghost"
      iconSize="sm"
      onClick={handleCopy}
      className={cn(
        'hover:bg-muted hover:text-muted-foreground size-6 transition-colors',
        className
      )}
      aria-label={isCopying ? 'Copied' : 'Copy'}
    />
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
