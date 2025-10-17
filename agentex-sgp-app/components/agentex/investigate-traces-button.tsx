import { cn } from '@/lib/utils';
import { forwardRef } from 'react';
import { ArrowRight } from 'lucide-react';
import { useAppConfig } from '@/hooks/use-app-config';

interface InvestigateTracesButtonProps {
  className?: string;
  disabled?: boolean;
  taskId: string;
}

export const InvestigateTracesButton = forwardRef<
  HTMLAnchorElement,
  InvestigateTracesButtonProps
>(({ className, disabled = false, taskId, ...props }, ref) => {
  const { sgpAppURL } = useAppConfig();
  const sgpTracesURL = `${sgpAppURL}/beta/monitor?trace_id=${taskId}&tt-trace-id=${taskId}`;

  return (
    <a
      ref={ref}
      href={sgpTracesURL}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        'flex items-center gap-2 text-black dark:text-gray-400 hover:text-gray-600 dark:hover:text-white transition-colors text-sm focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-20 rounded',
        disabled && 'cursor-not-allowed opacity-50 pointer-events-none',
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
