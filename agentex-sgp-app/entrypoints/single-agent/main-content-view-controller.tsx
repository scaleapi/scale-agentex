import { AgentexTask } from '@/components/agentex/agentex-task';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { toast } from 'react-toastify';
import { CreateTaskView } from './create-task-view';
import { Loading } from './loading';
import { Task } from './task';

export function MainContentViewController() {
  const { taskID } = useSafeSearchParams();

  if (taskID === null) {
    return <CreateTaskView />;
  }

  return (
    <AgentexTask
      taskID={taskID}
      fallback={<Loading />}
      onError={(error) => {
        console.error(error);

        const caughtErrorMessage: string | null =
          typeof error === 'object' &&
          error !== null &&
          'message' in error &&
          typeof error.message === 'string'
            ? error.message
            : null;

        toast.error(
          `Failed to load task: ID=${taskID} ${
            caughtErrorMessage ?? 'unknown error'
          }`
        );
      }}
    >
      <Task />
    </AgentexTask>
  );
}
