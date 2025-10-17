import {
  CreateUserMessageForm,
  CreateUserMessageFormContent,
} from '@/components/agentex/create-user-message-form';
import { TaskTopBar } from '@/components/agentex/task-top-bar';
import { useAgentexSingleAgentRootController } from '@/hooks/use-agentex-single-agent-root-controller';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useSafeTheme } from '@/hooks/use-safe-theme';
import { useState } from 'react';

export function CreateTaskView() {
  const { createTask } = useAgentexSingleAgentRootController();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const { setTaskID } = useSafeSearchParams();
  const [formDisabled, setFormDisabled] = useState(false);

  const theme = useSafeTheme();

  return (
    <div className="flex-1 flex flex-col h-full bg-task-background">
      <TaskTopBar taskId={null} />
      {/* Messages Area - Scrollable (empty for new chat) */}
      <div className="flex-1 overflow-y-auto bg-task-background">
        <div className="max-w-[800px] mx-auto w-full p-4"></div>
      </div>

      {/* Form Area - Consistent with Task component */}
      <div className="bg-task-background">
        <div className="max-w-[800px] mx-auto w-full p-4 mb-2">
          {errorMessage && (
            <div
              className="text-destructive mb-2"
              role="alert"
              aria-live="polite"
            >
              {errorMessage}
            </div>
          )}
          <CreateUserMessageForm
            agentOptions={[]}
            disabled={formDisabled}
            theme={theme}
            onSubmit={(data, resetForm) => {
              setErrorMessage(null);
              setFormDisabled(true);
              createTask(
                data.kind === 'data'
                  ? {
                      author: 'user',
                      type: 'data',
                      data: data.content,
                    }
                  : {
                      author: 'user',
                      type: 'text',
                      format: 'markdown',
                      content: data.content,
                    },
                null
              ).then(
                (task) => {
                  resetForm();
                  setTaskID(task.id);
                  setFormDisabled(false);
                },
                (error) => {
                  setFormDisabled(false);
                  console.error(error);
                  setErrorMessage('Failed to send message.');
                }
              );
            }}
          >
            <CreateUserMessageFormContent />
          </CreateUserMessageForm>
        </div>
      </div>
    </div>
  );
}
