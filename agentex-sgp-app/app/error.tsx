'use client';

import { AlertCircle } from 'lucide-react';

import { TaskTopBar } from '@/components/agentex/task-top-bar';
import { Button } from '@/components/ui/button';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="fixed inset-0 flex">
      {/* Main Content Area */}
      <div className="bg-task-background flex h-full flex-1 flex-col">
        <TaskTopBar taskId={null} />

        {/* Error Message - Centered */}
        <div className="flex flex-1 flex-col items-center justify-center p-8">
          <div className="w-full max-w-md space-y-6 text-center">
            <div className="flex justify-center">
              <div className="bg-destructive/10 rounded-full p-4">
                <AlertCircle className="text-destructive h-12 w-12" />
              </div>
            </div>

            <div className="space-y-2">
              <h1 className="text-2xl font-semibold">Something went wrong</h1>
              <p className="text-muted-foreground">
                We encountered an error while loading the agent.
              </p>
            </div>

            {error.message && (
              <div className="bg-destructive/10 rounded-lg p-4 text-left text-sm">
                <p className="text-destructive font-mono break-words">
                  {error.message}
                </p>
              </div>
            )}

            <div className="flex justify-center gap-3">
              <Button onClick={reset} variant="default">
                Try again
              </Button>
              <Button
                onClick={() => (window.location.href = '/')}
                variant="outline"
              >
                Go home
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
