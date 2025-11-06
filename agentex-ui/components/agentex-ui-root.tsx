'use client';

import { useCallback, useEffect, useState } from 'react';

import { ToastContainer } from 'react-toastify';

import { PrimaryContent } from '@/components/primary-content/primary-content';
import { AgentexProvider } from '@/components/providers';
import { TaskSidebar } from '@/components/task-sidebar/task-sidebar';
import { TracesSidebar } from '@/components/traces-sidebar/traces-sidebar';
import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

type AgentexUIRootProps = {
  sgpAppURL: string;
  agentexAPIBaseURL: string;
};

export function AgentexUIRoot({
  sgpAppURL,
  agentexAPIBaseURL,
}: AgentexUIRootProps) {
  const { agentName, taskID, updateParams } = useSafeSearchParams();
  const [isTracesSidebarOpen, setIsTracesSidebarOpen] = useState(false);
  const [localAgentName, setLocalAgentName] = useLocalStorageState<
    string | undefined
  >('lastSelectedAgent', undefined);

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

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Global cmd + k to trigger a new chat
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        handleSelectTask(null);
      }
      // Escape to clear the selected agent on the home page
      if (event.key === 'Escape' && !!agentName && !taskID) {
        updateParams({
          [SearchParamKey.AGENT_NAME]: null,
        });
        setLocalAgentName(undefined);
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleSelectTask, agentName, taskID, updateParams, setLocalAgentName]);

  return (
    <>
      <AgentexProvider
        sgpAppURL={sgpAppURL ?? ''}
        agentexAPIBaseURL={agentexAPIBaseURL}
      >
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
      </AgentexProvider>
      <ToastContainer />
    </>
  );
}
