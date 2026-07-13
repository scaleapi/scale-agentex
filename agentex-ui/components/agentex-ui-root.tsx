'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

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

type AgentexUIRootProps = {
  agentRunSchedulesEnabled: boolean;
};

export function AgentexUIRoot({
  agentRunSchedulesEnabled,
}: AgentexUIRootProps) {
  const { agentName, taskID, sgpAccountID, updateParams } =
    useSafeSearchParams();
  const [isTracesSidebarOpen, setIsTracesSidebarOpen] = useState(false);
  const { agentexClient } = useAgentexClient();
  const { data: agents = [], isFetching: isAgentsFetching } =
    useAgents(agentexClient);
  // Validate the deep-linked agent directly against the backend so a valid agent opens
  // even if it sits outside the loaded list (e.g. on accounts with many agents).
  const {
    data: agentByName,
    isFetching: isAgentByNameFetching,
    isError: isAgentByNameError,
  } = useAgentByName(agentexClient, agentName);
  const [localAgentName, setLocalAgentName] = useLocalStorageState<
    string | undefined
  >('lastSelectedAgent', undefined);
  const accountRef = useRef(sgpAccountID);

  // Wait until neither query is fetching before validating. We gate on `isFetching` (not
  // `isLoading`, which is false once a query has cached data) so we never validate against
  // stale data mid-refetch. A disabled by-name query reports `isFetching: false`, so it
  // doesn't block the localStorage-restore path when there's no agent_name. Deps are
  // intentionally narrowed so we re-validate on fetch settle / agent_name change.
  useEffect(() => {
    // An account switch resets to the home grid: the selected agent is account-scoped,
    // so a same-named agent in the new account must not stay selected.
    if (accountRef.current !== sgpAccountID) {
      accountRef.current = sgpAccountID;
      setLocalAgentName(undefined);
      if (agentName) updateParams({ [SearchParamKey.AGENT_NAME]: null });
      return;
    }

    if (isAgentsFetching || isAgentByNameFetching) return;

    // Accept an agent found in the (paginated) list OR resolved directly by name, so a valid
    // deep-linked agent opens even if it falls outside the loaded list.
    const agentInList = agents.find(agent => agent.name === agentName);
    const selectedAgent = agentInList ?? agentByName ?? undefined;
    const isAgentValid = selectedAgent && selectedAgent.status === 'Ready';

    // If the agent isn't in the loaded list and the by-name lookup errored (a transient
    // failure, not a 404), we can't tell whether it's valid — leave the URL alone rather
    // than bouncing a possibly-valid deep link to the home grid.
    const couldNotDetermine = !agentInList && isAgentByNameError;

    if (agentName && !isAgentValid && !couldNotDetermine) {
      updateParams({ [SearchParamKey.AGENT_NAME]: null });
      setLocalAgentName(undefined);
    }

    if (!agentName && localAgentName) {
      updateParams({ [SearchParamKey.AGENT_NAME]: localAgentName });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    sgpAccountID,
    isAgentsFetching,
    isAgentByNameFetching,
    isAgentByNameError,
    agentName,
  ]);

  const handleSelectTask = useCallback(
    (taskId: string | null) => {
      updateParams({
        [SearchParamKey.TASK_ID]: taskId,
        [SearchParamKey.VIEW]: null,
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
        <TaskSidebar agentRunSchedulesEnabled={agentRunSchedulesEnabled} />
        <PrimaryContent
          agentRunSchedulesEnabled={agentRunSchedulesEnabled}
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
