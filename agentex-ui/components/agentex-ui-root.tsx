'use client';

import { useCallback, useEffect, useState } from 'react';

import { ToastContainer } from 'react-toastify';

import { ArtifactPanel } from '@/components/artifacts/artifact-panel';
import { PrimaryContent } from '@/components/primary-content/primary-content';
import { useAgentexClient } from '@/components/providers';
import { TaskSidebar } from '@/components/task-sidebar/task-sidebar';
import { TracesSidebar } from '@/components/traces-sidebar/traces-sidebar';
import { useArtifactPanel } from '@/contexts/artifact-panel-context';
import { useAgents } from '@/hooks/use-agents';
import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

export function AgentexUIRoot() {
  const { agentName, taskID, updateParams } = useSafeSearchParams();
  const [isTracesSidebarOpen, setIsTracesSidebarOpen] = useState(false);
  const { agentexClient } = useAgentexClient();
  const { data: agents = [], isLoading } = useAgents(agentexClient);
  const { isOpen: isArtifactPanelOpen, closeArtifact } = useArtifactPanel();
  const [localAgentName, setLocalAgentName] = useLocalStorageState<
    string | undefined
  >('lastSelectedAgent', undefined);

  useEffect(() => {
    if (isLoading) return;

    const selectedAgent = agents.find(agent => agent.name === agentName);
    const isAgentValid = selectedAgent && selectedAgent.status === 'Ready';

    if (!isAgentValid) {
      updateParams({ [SearchParamKey.AGENT_NAME]: null });
      setLocalAgentName(undefined);
    }

    if (!agentName && localAgentName) {
      updateParams({ [SearchParamKey.AGENT_NAME]: localAgentName });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

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
      <ToastContainer />
    </>
  );
}
