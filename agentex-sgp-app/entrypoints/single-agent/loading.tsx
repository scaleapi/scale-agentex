import {
  CreateUserMessageForm,
  CreateUserMessageFormContent,
} from '@/components/agentex/create-user-message-form';
import { TaskTopBar } from '@/components/agentex/task-top-bar';
import { useSafeTheme } from '@/hooks/use-safe-theme';

export function Loading() {
  const theme = useSafeTheme();

  return (
    <div className="flex flex-1 flex-col h-full bg-task-background">
      <TaskTopBar taskId={null} />

      {/* Messages Area - Scrollable (empty) */}
      <div className="flex flex-col flex-1 overflow-y-auto items-center"></div>

      {/* Form Area - Sticky Bottom */}
      <div className="max-w-[800px] mx-auto w-full p-4 mb-2">
        <CreateUserMessageForm
          agentOptions={[]}
          disabled={true}
          theme={theme}
          onSubmit={() => {
            // No-op during loading
          }}
        >
          <CreateUserMessageFormContent />
        </CreateUserMessageForm>
      </div>
    </div>
  );
}
