'use client';

import { TaskTopBar } from '@/components/agentex/task-top-bar';
import { Button } from '@/components/ui/button';
import { AlertCircle } from 'lucide-react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex fixed inset-0">
      {/* Main Content Area */}
      <div className="flex flex-1 flex-col h-full bg-task-background">
        <TaskTopBar taskId={null} />

        {/* Error Message - Centered */}
        <div className="flex flex-col flex-1 items-center justify-center p-8">
          <div className="max-w-md w-full text-center space-y-6">
            <div className="flex justify-center">
              <div className="rounded-full bg-destructive/10 p-4">
                <AlertCircle className="h-12 w-12 text-destructive" />
              </div>
            </div>

            <div className="space-y-2">
              <h1 className="text-2xl font-semibold">Something went wrong</h1>
              <p className="text-muted-foreground">
                We encountered an error while loading the agent.
              </p>
            </div>

            {error.message && (
              <div className="bg-destructive/10 rounded-lg p-4 text-sm text-left">
                <p className="font-mono text-destructive break-words">
                  {error.message}
                </p>
              </div>
            )}

            <div className="flex gap-3 justify-center">
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
