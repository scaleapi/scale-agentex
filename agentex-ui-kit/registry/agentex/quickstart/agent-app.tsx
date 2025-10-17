"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { AgentexSingleAgentRoot } from "@/registry/agentex/agentex-single-agent-root/components/agentex-single-agent-root";
import { Header } from "@/registry/agentex/quickstart/header";
import { MainViewController } from "@/registry/agentex/quickstart/main-view-controller";
import AgentexSDK from "agentex";
import type { Agent } from "agentex/resources";
import { Suspense, useMemo } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { toast, ToastContainer } from "react-toastify";

type Props = {
  agentName: Agent["name"];
  agentexAPIBaseURL: string;
};

/**
 * This is the main entrypoint for your app!
 *
 * This basic one does this
 * 1. Creates the agentex root context so the rest of your app has access to your agent and tasks
 * 2. Renders a header
 * 3. Renders the main content
 */
function AgentAppImpl({ agentexAPIBaseURL, agentName }: Props) {
  const agentexClient = useMemo(
    () => new AgentexSDK({ baseURL: agentexAPIBaseURL }),
    [agentexAPIBaseURL]
  );

  return (
    <div className="min-h-screen flex flex-col">
      <AgentexSingleAgentRoot
        agentexClient={agentexClient}
        agentName={agentName}
        fallback={<Skeleton className="mx-2 flex-1 h-96" />}
        onError={(error) => {
          console.error(error);

          const caughtErrorMessage: string | null =
            typeof error === "object" &&
            error !== null &&
            "message" in error &&
            typeof error.message === "string"
              ? error.message
              : null;

          toast.error(caughtErrorMessage ?? "Unknown error");
        }}
      >
        <Header />

        <main className="flex-1 flex justify-center">
          {/*
            * This is your main content!
            *
            * Right now it just displays a chatgpt.com style UI, but you can move that to a sidebar or whatever you want.
            */}

          <div className="flex-1 max-w-[min(100%-var(--spacing)*4,var(--spacing)*256)] my-8">
            <Suspense fallback={<Skeleton className="flex-1 h-96" />}>
              <MainViewController />
            </Suspense>
          </div>
        </main>
      </AgentexSingleAgentRoot>
    </div>
  );
}

/**
 * This is just a wrapper for AgentAppImpl that adds
 * 1. ErrorBoundary
 * 2. ToastContainer (for error messages)
 */
export function AgentApp({ ...props }: Props) {
  return (
    <ErrorBoundary
      fallbackRender={({ error }) => (
        <div role="alert">
          <p>Oops! An unexpected error occurred.</p>
          <pre className="text-destructive">{error.message}</pre>
        </div>
      )}
    >
      <AgentAppImpl {...props} />
      <ToastContainer />
    </ErrorBoundary>
  );
}
