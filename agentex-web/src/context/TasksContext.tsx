'use client';

import AgentexSDK from 'agentex';
import type {Task, TextContent} from 'agentex/resources';
import {createContext, useContext, useEffect, useState} from 'react';

const BASE_URL = process.env.AGENTEX_BASE_URL || 'http://localhost:5003';

const client = new AgentexSDK({baseURL: BASE_URL, apiKey: 'dummy'});

interface PendingMessage {
  content: TextContent;
  agentId: string;
  taskId: Task['id'];
}

interface TasksContextType {
  tasks: Task[];
  selectedTask: Task | null;
  setSelectedTask: (task: Task | null) => void;
  refreshTasks: () => Promise<void>;
  isLoading: boolean;
  pendingMessage: PendingMessage | null;
  setPendingMessage: (message: PendingMessage | null) => void;
  clearPendingMessage: () => void;
}

const TasksContext = createContext<TasksContextType>({
  tasks: [],
  selectedTask: null,
  setSelectedTask: () => {},
  refreshTasks: async () => {},
  isLoading: true,
  pendingMessage: null,
  setPendingMessage: () => {},
  clearPendingMessage: () => {},
});

export function TasksProvider({children}: {children: React.ReactNode}) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [pendingMessage, setPendingMessageState] = useState<PendingMessage | null>(null);

  const setPendingMessage = (message: PendingMessage | null) => {
    setPendingMessageState(message);
  };

  const clearPendingMessage = () => {
    setPendingMessageState(null);
  };

  const refreshTasks = async () => {
    try {
      const response = await client.tasks.list();
      setTasks(response);
    } catch (error) {
      console.error('Error fetching tasks:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // useEffect(() => {
  //   refreshTasks();

  //   // Set up polling for task updates
  //   const interval = setInterval(refreshTasks, 5000);
  //   return () => clearInterval(interval);
  // }, []);

  useEffect(() => {
    refreshTasks();
  }, []);

  return (
    <TasksContext.Provider
      value={{
        tasks,
        selectedTask,
        setSelectedTask,
        refreshTasks,
        isLoading,
        pendingMessage,
        setPendingMessage,
        clearPendingMessage,
      }}
    >
      {children}
    </TasksContext.Provider>
  );
}

export const useTasks = () => useContext(TasksContext);
