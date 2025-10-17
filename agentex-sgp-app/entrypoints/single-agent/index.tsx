'use client';

import { AppConfigProvider, useAppConfig } from '@/hooks/use-app-config';
import { useMemo } from 'react';
import { ToastContainer } from 'react-toastify';

import { AgentexSingleAgentRoot } from '@/components/agentex/agentex-single-agent-root';
import { TaskSidebar } from '@/components/agentex/task-sidebar';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import AgentexSDK from 'agentex';
import { MainContentViewController } from './main-content-view-controller';

type ImplProps = {
  agentName: string;
};

function SingleAgentImpl({ agentName }: ImplProps) {
  const { agentexAPIBaseURL } = useAppConfig();
  const agentexClient = useMemo(
    () =>
      new AgentexSDK({
        baseURL: agentexAPIBaseURL,
      }),
    [agentexAPIBaseURL]
  );

  const { taskID, setTaskID } = useSafeSearchParams();

  return (
    <AgentexSingleAgentRoot agentexClient={agentexClient} agentName={agentName}>
      <div className="flex fixed inset-0">
        <TaskSidebar selectedTaskID={taskID} onSelectTask={setTaskID} />
        <MainContentViewController />
      </div>
    </AgentexSingleAgentRoot>
  );
}

type Props = ImplProps & {
  sgpAppURL: string;
  agentexAPIBaseURL: string;
};

export function SingleAgent({ sgpAppURL, agentexAPIBaseURL, ...props }: Props) {
  return (
    <>
      <AppConfigProvider
        sgpAppURL={sgpAppURL}
        agentexAPIBaseURL={agentexAPIBaseURL}
      >
        <SingleAgentImpl {...props} />
      </AppConfigProvider>
      <ToastContainer />
    </>
  );
}
