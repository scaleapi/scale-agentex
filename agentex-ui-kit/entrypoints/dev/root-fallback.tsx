import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AgentexDevClientSetupForm,
  AgentexDevClientSetupFormContent,
  AgentexDevClientSetupFormTrigger,
} from "@/registry/agentex/agentex-dev-root/components/agentex-dev-client-setup-form";
import { memo } from "react";

type Props = {
  errorMessage: string | null;
};

function RootFallbackImpl({ errorMessage }: Props) {
  return (
    <>
      <AgentexDevClientSetupForm>
        <header className="w-full sm:sticky mt-4 sm:top-0 sm:z-10 bg-background">
          <div className="mx-auto max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width))]">
            <div className="my-2 flex flex-col items-center-safe gap-2 sm:flex-row sm:items-baseline-last sm:justify-between">
              <h1>Agentex UI</h1>
              <div className="flex items-baseline-last justify-center-safe sm:justify-end-safe gap-2">
                <AgentexDevClientSetupFormTrigger asChild>
                  <Button variant="outline">Client Setup</Button>
                </AgentexDevClientSetupFormTrigger>
                <div className="h-9 w-32 shrink-0" />
              </div>
            </div>
          </div>
        </header>
        <main className="flex-1 flex justify-center">
          {errorMessage ? (
            <div className="text-destructive font-bold text-lg m-4">
              {errorMessage}
            </div>
          ) : (
            <Skeleton className="flex-1 max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width))] my-8 h-96" />
          )}
        </main>
        <AgentexDevClientSetupFormContent
          side="bottom"
          className="pt-4 pb-24 px-8 max-h-3/4 overflow-auto"
        />
      </AgentexDevClientSetupForm>
    </>
  );
}

export const RootFallback = memo(RootFallbackImpl);
