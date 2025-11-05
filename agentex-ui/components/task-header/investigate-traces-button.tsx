'use client';

import { forwardRef } from 'react';

import { ArrowRight } from 'lucide-react';

import { useAgentexClient } from '@/components/providers';
import { cn } from '@/lib/utils';

type InvestigateTracesButtonProps = {
  className?: string;
  disabled?: boolean;
  taskId: string;
};

export const InvestigateTracesButton = forwardRef<
  HTMLAnchorElement,
  InvestigateTracesButtonProps
>(({ className, disabled = false, taskId, ...props }, ref) => {
  const { sgpAppURL } = useAgentexClient();
  const sgpTracesURL = `${sgpAppURL}/beta/monitor?trace_id=${taskId}&tt-trace-id=${taskId}`;

  if (!sgpAppURL) {
    return null;
  }

  return (
    <a
      ref={ref}
      href={sgpTracesURL}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        'focus:ring-opacity-20 flex items-center gap-2 rounded text-sm text-black transition-colors hover:text-gray-600 focus:ring-2 focus:ring-white focus:outline-none dark:text-gray-400 dark:hover:text-white',
        disabled && 'pointer-events-none cursor-not-allowed opacity-50',
        className
      )}
      {...props}
    >
      Investigate traces
      <ArrowRight className="h-3 w-3" />
    </a>
  );
});

InvestigateTracesButton.displayName = 'InvestigateTracesButton';
