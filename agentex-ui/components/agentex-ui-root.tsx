'use client';

import { useCallback, useEffect, useState } from 'react';

import { ToastContainer } from 'react-toastify';

import { PrimaryContent } from '@/components/primary-content/primary-content';
import { useAgentexClient } from '@/components/providers';
import { TaskSidebar } from '@/components/task-sidebar/task-sidebar';
import { TracesSidebar } from '@/components/traces-sidebar/traces-sidebar';
import { useAgentByName } from '@/hooks/use-agent-by-name';
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
  // Validate the deep-linked agent directly against the backend so a valid agent opens
  // even if it sits outside the loaded list (e.g. on accounts with many agents).
  const { data: agentByName, isLoading: isAgentByNameLoading } = useAgentByName(
    agentexClient,
    agentName
  );
  const [localAgentName, setLocalAgentName] = useLocalStorageState<
    string | undefined
  >('lastSelectedAgent', undefined);

  // Gate on `isLoading` (not `isPending`): a disabled by-name query stays `pending` forever,
  // but `isLoading` is `pending && fetching`, so it's false while disabled — letting the
  // localStorage-restore branch run when no agent_name is present. Deps are intentionally
  // narrowed to the load-settled flags + agentName so we re-validate on load completion and
  // on agent_name changes, not on every `agents`/`agentByName` identity change.
  useEffect(() => {
    if (isLoading || isAgentByNameLoading) return;

    // Accept an agent found in the (paginated) list OR resolved directly by name, so a valid
    // deep-linked agent opens even if it falls outside the loaded list.
    const selectedAgent =
      agents.find(agent => agent.name === agentName) ??
      agentByName ??
      undefined;
    const isAgentValid = selectedAgent && selectedAgent.status === 'Ready';

    if (agentName && !isAgentValid) {
      updateParams({ [SearchParamKey.AGENT_NAME]: null });
      setLocalAgentName(undefined);
    }

    if (!agentName && localAgentName) {
      updateParams({ [SearchParamKey.AGENT_NAME]: localAgentName });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, isAgentByNameLoading, agentName]);

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
        />
        <TracesSidebar isOpen={isTracesSidebarOpen} />
      </div>
      <ToastContainer />
    </>
  );
}
