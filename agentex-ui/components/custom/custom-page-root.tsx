'use client';

import { useCallback, useState } from 'react';

import { ToastContainer } from 'react-toastify';

import { useAgentexClient } from '@/components/providers';
import { ResizableSidebar } from '@/components/ui/resizable-sidebar';
import { useAgents } from '@/hooks/use-agents';

import { ConfigPanel, DEFAULT_CONFIG } from './config-panel';
import { CustomChatPanel } from './custom-chat-panel';
import { CustomPromptInput } from './custom-prompt-input';

import type { GoldenAgentConfig } from './config-panel';

const GOLDEN_AGENT_NAME = 'golden-agent';

export function CustomPageRoot() {
  const { agentexClient } = useAgentexClient();
  const { data: agents = [], isLoading } = useAgents(agentexClient);

  const [config, setConfig] = useState<GoldenAgentConfig>(DEFAULT_CONFIG);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [isConfigLocked, setIsConfigLocked] = useState(false);
  const [prompt, setPrompt] = useState('');

  const goldenAgent = agents.find(a => a.name === GOLDEN_AGENT_NAME);

  const handleTaskCreated = useCallback((newTaskId: string) => {
    setTaskId(newTaskId);
    setIsConfigLocked(true);
  }, []);

  const handleReset = useCallback(() => {
    setTaskId(null);
    setIsConfigLocked(false);
    setPrompt('');
  }, []);

  const handleConfigChange = useCallback(
    (newConfig: GoldenAgentConfig) => {
      if (!isConfigLocked) {
        setConfig(newConfig);
      }
    },
    [isConfigLocked]
  );

  if (isLoading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <p className="text-muted-foreground text-sm">Loading agents...</p>
      </div>
    );
  }

  if (!goldenAgent) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm font-medium">golden-agent not found</p>
          <p className="text-muted-foreground mt-1 text-xs">
            Make sure the golden-agent is deployed and has status Ready.
          </p>
        </div>
      </div>
    );
  }

  if (goldenAgent.status !== 'Ready') {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm font-medium">golden-agent is not ready</p>
          <p className="text-muted-foreground mt-1 text-xs">
            Current status: {goldenAgent.status}
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="fixed inset-0 flex w-full">
        <ResizableSidebar
          side="left"
          storageKey="custom-config-width"
          defaultWidth={400}
          minWidth={300}
          maxWidth={600}
        >
          <ConfigPanel
            disabled={isConfigLocked}
            onConfigChange={handleConfigChange}
            onReset={handleReset}
          />
        </ResizableSidebar>

        <main className="flex min-w-0 flex-1 flex-col">
          <CustomChatPanel taskId={taskId} />

          <div className="flex w-full justify-center border-t px-4 py-4">
            <CustomPromptInput
              taskId={taskId}
              config={config}
              prompt={prompt}
              setPrompt={setPrompt}
              onTaskCreated={handleTaskCreated}
            />
          </div>
        </main>
      </div>
      <ToastContainer />
    </>
  );
}
