'use client';

import { ExternalLink } from 'lucide-react';

import { useArtifactPanel } from '@/contexts/artifact-panel-context';

interface ExternalEventCalloutProps {
  event: string;
  url: string;
}

export function ExternalEventCallout({
  event,
  url,
}: ExternalEventCalloutProps) {
  const {
    openArtifact,
    closeArtifact,
    isOpen,
    url: currentUrl,
  } = useArtifactPanel();

  const handleClick = () => {
    // Toggle if clicking the same external event that's already open
    if (isOpen && currentUrl === url) {
      closeArtifact();
    } else {
      openArtifact(url, event);
    }
  };

  return (
    <button
      onClick={handleClick}
      className="group w-full cursor-pointer text-left transition-all hover:scale-[1.01] active:scale-[0.99]"
    >
      <div className="flex items-center gap-2 rounded-md border border-orange-300 bg-gradient-to-r from-orange-50 to-yellow-50 px-3 py-2 shadow-sm transition-shadow hover:shadow-md dark:border-orange-700 dark:from-orange-950 dark:to-yellow-950">
        <ExternalLink className="h-4 w-4 flex-shrink-0 text-orange-600 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 dark:text-orange-400" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-orange-900 dark:text-orange-100">
          {event}
        </span>
        <span className="flex-shrink-0 text-xs text-orange-600 dark:text-orange-500">
          View
        </span>
      </div>
    </button>
  );
}
