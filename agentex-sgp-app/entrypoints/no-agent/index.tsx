'use client';

import { useState } from 'react';
import { ErrorBoundary } from 'react-error-boundary';
import { toast, ToastContainer } from 'react-toastify';
import { AgentsList } from './agents-list';
import { Header } from './header';
import { AgentexNoAgentRoot } from './no-agent-root';
import { RootFallback } from './root-fallback';
import { AppConfigProvider } from '@/hooks/use-app-config';

function NoAgentImpl() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  return (
    <div className="min-h-screen flex flex-col">
      <AgentexNoAgentRoot
        fallback={<RootFallback errorMessage={errorMessage} />}
        onError={(error) => {
          console.error(error);

          const caughtErrorMessage: string | null =
            typeof error === 'object' &&
            error !== null &&
            'message' in error &&
            typeof error.message === 'string'
              ? error.message
              : null;

          toast.error(caughtErrorMessage ?? 'Unknown error');
          setErrorMessage(caughtErrorMessage ?? 'Unknown error');
        }}
      >
        <Header />
        <main className="flex-1 flex justify-center">
          <div className="flex-1 max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width))] my-8">
            <AgentsList />
          </div>
        </main>
      </AgentexNoAgentRoot>
    </div>
  );
}

type Props = {
  sgpAppURL: string;
  agentexAPIBaseURL: string;
};

export function NoAgent({ sgpAppURL, agentexAPIBaseURL }: Props) {
  return (
    <ErrorBoundary
      fallbackRender={({ error }) => (
        <div role="alert">
          <p>Oops! An unexpected error occurred.</p>
          <pre className="text-destructive">{error.message}</pre>
        </div>
      )}
    >
      <AppConfigProvider
        sgpAppURL={sgpAppURL ?? ''}
        agentexAPIBaseURL={agentexAPIBaseURL}
      >
        <NoAgentImpl />
      </AppConfigProvider>
      <ToastContainer />
    </ErrorBoundary>
  );
}
