'use client';

import { useCallback, useEffect, useState } from 'react';

import { ToastContainer } from 'react-toastify';

import { PrimaryContent } from '@/app/primary-content';
import { ArtifactPanel } from '@/components/agentex/artifact-panel';
import { TaskSidebar } from '@/components/agentex/task-sidebar';
import { TracesSidebar } from '@/components/agentex/traces-sidebar';
import { AgentexProvider } from '@/components/providers';
import { useArtifactPanel } from '@/contexts/artifact-panel-context';
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
  const { isOpen: isArtifactPanelOpen, closeArtifact } = useArtifactPanel();
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

  // Close artifact when task or agent changes
  useEffect(() => {
    if (isArtifactPanelOpen) {
      closeArtifact();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskID, agentName]);

  // Close traces sidebar when artifact opens
  useEffect(() => {
    if (isArtifactPanelOpen && isTracesSidebarOpen) {
      setIsTracesSidebarOpen(false);
    }
  }, [isArtifactPanelOpen, isTracesSidebarOpen]);

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
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleSelectTask, agentName, taskID, updateParams]);

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
            isArtifactPanelOpen={isArtifactPanelOpen}
          />
          <TracesSidebar isOpen={isTracesSidebarOpen} />
          <ArtifactPanel />
        </div>
      </AgentexProvider>
      <ToastContainer />
    </>
  );
}
