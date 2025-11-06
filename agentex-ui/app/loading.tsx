'use client';

import { Suspense } from 'react';

import { ArrowUp } from 'lucide-react';

import { IconButton } from '@/components/ui/icon-button';
import { Skeleton } from '@/components/ui/skeleton';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';

function LoadingContent() {
  const { taskID } = useSafeSearchParams();

  // If there's a task ID, show the task/chat loading state
  if (taskID) {
    return (
      <div className="fixed inset-0 flex w-full">
        <div className="bg-background border-border flex h-full w-64 flex-col border-r">
          <div className="border-border border-b p-4">
            <div className="flex items-center gap-2 pb-4">
              <Skeleton className="h-6 w-24" />
            </div>
            <Skeleton className="h-10 w-full" />
          </div>
          <div className="flex flex-col gap-5 overflow-y-auto py-4 pr-2 pl-4">
            {[...Array(8)].map((_, i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </div>
        </div>
        <div className="bg-task-background flex h-full flex-1 flex-col">
          <div className="border-border border-b px-4 py-3">
            <Skeleton className="h-8 w-48" />
          </div>
          <div className="flex flex-1 flex-col items-center overflow-y-auto px-4 pt-4">
            <div className="flex w-full max-w-[800px] flex-col gap-4">
              <div className="flex justify-end">
                <Skeleton className="h-15 w-1/4 rounded-lg" />
              </div>
              <div className="flex flex-col justify-start gap-3">
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-7/8" />
                <Skeleton className="h-4 w-5/8" />
              </div>
              <div className="flex justify-end">
                <Skeleton className="h-15 w-1/4 rounded-lg" />
              </div>
              <div className="flex flex-col justify-start gap-3">
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-7/8" />
                <Skeleton className="h-4 w-5/8" />
              </div>
            </div>
          </div>
          <div className="flex w-full justify-center px-4 py-8 sm:px-6 md:px-8">
            <div className="w-full max-w-3xl">
              <Skeleton className="h-[58px] w-full rounded-full" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // If there's no task ID, show the home loading state
  return (
    <div className="fixed inset-0 flex w-full">
      <div className="flex h-full flex-1 flex-col justify-center">
        <div className="flex items-center justify-center">
          <div className="flex flex-col items-center justify-center gap-6 px-4">
            <div className="text-2xl font-bold">Select an Agent:</div>
            <div className="flex max-w-4xl flex-wrap items-center justify-center gap-2">
              {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-9.5 w-32 rounded-full" />
              ))}
            </div>
          </div>
        </div>
        <div className="flex w-full justify-center px-4 py-8 sm:px-6 md:px-8">
          <div className="w-full max-w-3xl">
            <div className="w-full opacity-50">
              <div className="border-input dark:bg-input/30 disabled:bg-accent flex w-full justify-between rounded-full border bg-transparent py-2 pr-2 pl-6 disabled:cursor-not-allowed">
                <input
                  type="text"
                  value=""
                  disabled
                  placeholder="Select an agent to start"
                  className="mr-2 flex-1 outline-none focus:ring-0 focus:outline-none"
                  readOnly
                />
                <IconButton
                  className="pointer-events-auto size-10 rounded-full"
                  disabled
                  icon={ArrowUp}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Loading() {
  return (
    <Suspense
      fallback={
        <div className="fixed inset-0 flex items-center justify-center">
          <Skeleton className="h-8 w-32" />
        </div>
      }
    >
      <LoadingContent />
    </Suspense>
  );
}
