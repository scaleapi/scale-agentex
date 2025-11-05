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
      className="group w-full cursor-pointer text-left transition-all hover:scale-[1.02] active:scale-[0.98]"
    >
      <div className="rounded-lg border border-orange-300 bg-gradient-to-r from-orange-50 to-yellow-50 p-4 shadow-sm transition-shadow hover:shadow-md dark:border-orange-700 dark:from-orange-950 dark:to-yellow-950">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex-shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-orange-100 dark:bg-orange-900">
              <ExternalLink className="h-4 w-4 text-orange-600 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 dark:text-orange-400" />
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <span className="text-xs font-medium tracking-wide text-orange-700 uppercase dark:text-orange-400">
                External Event
              </span>
            </div>
            <p className="text-sm font-medium break-words text-orange-900 dark:text-orange-100">
              {event}
            </p>
            <p className="mt-2 flex items-center gap-1 text-xs text-orange-600 dark:text-orange-500">
              <span>Click to view</span>
              <ExternalLink className="h-3 w-3" />
            </p>
          </div>
        </div>
      </div>
    </button>
  );
}
