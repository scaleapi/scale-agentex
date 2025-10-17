import { BackToSGPLink } from '@/components/agentex/back-to-sgp-link';
import { ThemeToggle } from '@/components/agentex/theme-toggle';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useSingleAgent } from '@/hooks/use-single-agent';
import type { Agent } from 'agentex/resources';
import { memo, Suspense } from 'react';

type ImplProps = {
  agent: Agent;
};

function HeaderImpl({ agent }: ImplProps) {
  const { taskID, setTaskID } = useSafeSearchParams();

  return (
    <header className="w-full sticky top-0 z-10 bg-background p-4 border-b border-gray-600">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <BackToSGPLink />
          <button
            className="hover:underline hover:text-accent-foreground"
            onClick={() => setTaskID(null)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setTaskID(null);
              }
            }}
          >
            <h1 className="text-xl font-semibold text-white">
              Agentex: {agent.name}
            </h1>
          </button>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {taskID !== null && (
            <button
              className="p-2 hover:bg-accent hover:text-accent-foreground rounded-md transition-colors"
              type="button"
              onClick={() => {
                setTaskID(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setTaskID(null);
                }
              }}
              aria-label="New task"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                className="text-muted-foreground"
              >
                <g clipPath="url(#clip0_853_17351)">
                  <path
                    d="M8.75 0.500977H3.25C1.733 0.500977 0.5 1.73498 0.5 3.25098V11.251C0.5 11.548 0.675 11.817 0.947 11.937C1.044 11.98 1.148 12.001 1.25 12.001C1.433 12.001 1.614 11.934 1.754 11.806L4.29 9.50098H8.75C10.267 9.50098 11.5 8.26798 11.5 6.75098V3.25098C11.5 1.73398 10.267 0.500977 8.75 0.500977Z"
                    fill="currentColor"
                  />
                </g>
                <defs>
                  <clipPath id="clip0_853_17351">
                    <rect width="12" height="12" fill="white" />
                  </clipPath>
                </defs>
              </svg>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

function SuspendedHeader() {
  const agent = useSingleAgent();

  return (
    <Suspense
      fallback={
        <header className="w-full sticky top-0 z-10 bg-background p-4 border-b border-gray-600">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <BackToSGPLink />
              <h1 className="text-xl font-semibold text-white">
                Agentex: {agent.name}
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
            </div>
          </div>
        </header>
      }
    >
      <HeaderImpl agent={agent} />
    </Suspense>
  );
}

export const Header = memo(SuspendedHeader);
