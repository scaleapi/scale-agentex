"use client";

import {
  AgentexDevClientSetupForm,
  AgentexDevClientSetupFormContent,
} from "@/registry/agentex/agentex-dev-root/components/agentex-dev-client-setup-form";
import { AgentexDevRoot } from "@/registry/agentex/agentex-dev-root/components/agentex-dev-root";
import { useState } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { toast, ToastContainer } from "react-toastify";
import { Header } from "./header";
import { MainContentViewController } from "./main-content-view-controller";
import { RootFallback } from "./root-fallback";

function AgentexDevImpl() {
  const [selectedTaskID, setSelectedTask] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  return (
    <div className="min-h-screen p-4 flex flex-col">
      <AgentexDevRoot
        fallback={<RootFallback errorMessage={errorMessage} />}
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
          setErrorMessage(caughtErrorMessage ?? "Unknown error");
        }}
      >
        <AgentexDevClientSetupForm>
          <Header
            onSelectTask={setSelectedTask}
            selectedTaskID={selectedTaskID}
          />
          <main className="flex-1 flex justify-center">
            <div className="flex-1 max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width))] my-8">
              <MainContentViewController
                selectedTaskID={selectedTaskID}
                setSelectedTask={setSelectedTask}
              />
            </div>
          </main>
          <AgentexDevClientSetupFormContent
            side="bottom"
            className="pt-4 pb-24 px-8 max-h-3/4 overflow-auto"
          />
        </AgentexDevClientSetupForm>
      </AgentexDevRoot>
    </div>
  );
}

export function AgentexDev() {
  return (
    <ErrorBoundary
      fallbackRender={({ error }) => (
        <div role="alert">
          <p>ErrorBoundary triggered!</p>
          <pre className="text-destructive">{error.message}</pre>
        </div>
      )}
    >
      <AgentexDevImpl />
      <ToastContainer />
    </ErrorBoundary>
  );
}
