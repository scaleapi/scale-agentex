'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';

import { ToastContainer } from 'react-toastify';

import { TaskSidebar } from '@/components/agentex/task-sidebar';
import { TracesSidebar } from '@/components/agentex/traces-sidebar';
import { AgentexProvider } from '@/components/providers';
import { QueryProvider } from '@/components/providers/query-provider';
import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

import { PrimaryContent } from './primary-content';

type AgentexUIRootProps = {
  sgpAppURL: string;
  agentexAPIBaseURL: string;
};

export function AgentexUIRoot({
  sgpAppURL,
  agentexAPIBaseURL,
}: AgentexUIRootProps) {
  const { agentName, updateParams } = useSafeSearchParams();
  const [isTracesSidebarOpen, setIsTracesSidebarOpen] = useState(false);
  const [localAgentName] = useLocalStorageState<string | undefined>(
    'lastSelectedAgent',
    undefined
  );

  useEffect(() => {
    if (!agentName && localAgentName) {
      updateParams({ [SearchParamKey.AGENT_NAME]: localAgentName });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectTask = useCallback(
    (taskId: string | null) => {
      updateParams({
        [SearchParamKey.TASK_ID]: taskId,
      });
    },
    [updateParams]
  );

  // Global keyboard shortcut: cmd + k for new chat
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        handleSelectTask(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleSelectTask]);

  return (
    <QueryProvider>
      <AgentexProvider
        sgpAppURL={sgpAppURL ?? ''}
        agentexAPIBaseURL={agentexAPIBaseURL}
      >
        <Suspense fallback={<div>Loading...</div>}>
          <div className="fixed inset-0 flex w-full">
            <TaskSidebar />
            <PrimaryContent
              isTracesSidebarOpen={isTracesSidebarOpen}
              toggleTracesSidebar={() =>
                setIsTracesSidebarOpen(!isTracesSidebarOpen)
              }
            />
            <TracesSidebar isOpen={isTracesSidebarOpen} />
          </div>
        </Suspense>
      </AgentexProvider>
      <ToastContainer />
    </QueryProvider>
  );
}
