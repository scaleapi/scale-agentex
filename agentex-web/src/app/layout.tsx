'use client';

import {Button} from '@/components/ui/button';
import {ScrollArea} from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import {
  Sidebar,
  SidebarContent,
  SidebarProvider,
  SidebarRail,
} from '@/components/ui/sidebar';
import {TasksProvider, useTasks} from '@/context/TasksContext';
import AgentexSDK from 'agentex';
import type {Task} from 'agentex/resources';
import {
  CheckCircle2,
  Circle,
  CircleEllipsis,
  Menu,
  PenSquare,
  StopCircle,
  XCircle,
} from 'lucide-react';
import {Inter} from 'next/font/google';
import localFont from 'next/font/local';
import Link from 'next/link';
import {useEffect, useRef, useState} from 'react';
import './globals.css';

const BASE_URL = process.env.AGENTEX_BASE_URL || 'http://localhost:5003';

const client = new AgentexSDK({
  baseURL: BASE_URL,
  apiKey: 'dummy',
});

const geistSans = localFont({
  src: '../../public/fonts/GeistVF.woff',
  variable: '--font-geist-sans',
  weight: '100 900',
});

const geistMono = localFont({
  src: '../../public/fonts/GeistMonoVF.woff',
  variable: '--font-geist-mono',
  weight: '100 900',
});

// If loading a variable font, you don't need to specify the font weight
const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
});

type NonNullable<T> = T extends null | undefined ? never : T;

const statusIcons: {
  [key in NonNullable<Task['status']>]: {icon: React.ComponentType; color: string};
} = {
  COMPLETED: {icon: CheckCircle2, color: 'text-green-500'},
  FAILED: {icon: XCircle, color: 'text-red-500'},
  CANCELED: {icon: StopCircle, color: 'text-gray-500'},
  RUNNING: {icon: CircleEllipsis, color: 'text-blue-500'},
  TERMINATED: {icon: Circle, color: 'text-gray-500'},
  TIMED_OUT: {icon: Circle, color: 'text-orange-500'},
};

const SidebarContents = () => {
  const {tasks, selectedTask, setSelectedTask, isLoading} = useTasks();
  const [taskMessages, setTaskMessages] = useState<Record<string, string>>({});
  const [isFetchingMessages, setIsFetchingMessages] = useState(false);
  const previousTaskIds = useRef<Set<string>>(new Set());

  // Filter for tasks and sort by last update time
  const sortedTasks = [...tasks].sort((a, b) => {
    const aTime = new Date(a.updated_at || a.created_at || 0).getTime();
    const bTime = new Date(b.updated_at || b.created_at || 0).getTime();
    return bTime - aTime || (a.id > b.id ? -1 : 1);
  });

  // Fetch first message for each task - only for new tasks
  useEffect(() => {
    const fetchTaskMessages = async () => {
      if (isFetchingMessages) return;

      // Get the current task IDs
      const currentTaskIds = new Set(sortedTasks.map(task => task.id));

      // Find new tasks that we haven't fetched messages for yet
      const newTasks = sortedTasks.filter(
        task => !previousTaskIds.current.has(task.id) && !taskMessages[task.id]
      );

      if (newTasks.length === 0) return;

      setIsFetchingMessages(true);

      try {
        // Fetch messages only for new tasks
        const messagePromises = newTasks.map(async task => {
          try {
            const messages = await client.messages.list({task_id: task.id, limit: 1});
            const firstMessage = messages[0];

            if (
              firstMessage &&
              'content' in firstMessage.content &&
              typeof firstMessage.content.content === 'string'
            ) {
              return [task.id, firstMessage.content.content] as const;
            }
            return [task.id, 'No message content'] as const;
          } catch (error) {
            console.error(`Error fetching messages for task ${task.id}:`, error);
            return [task.id, 'Error loading message'] as const;
          }
        });

        const newMessages = await Promise.all(messagePromises);

        setTaskMessages(prev => ({
          ...prev,
          ...Object.fromEntries(newMessages),
        }));

        // Update the set of task IDs we've fetched messages for
        previousTaskIds.current = currentTaskIds;
      } finally {
        setIsFetchingMessages(false);
      }
    };

    fetchTaskMessages();
  }, [sortedTasks, isFetchingMessages, taskMessages]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b p-4">
        <Link href="/" className="flex cursor-pointer items-center space-x-2">
          <h2 className="pl-2 text-lg font-semibold">Agentex</h2>
        </Link>
        <div className="hidden gap-2 lg:flex">
          <Link href="/">
            <Button variant="ghost" size="icon" aria-label="New Task">
              <PenSquare className="h-5 w-5" />
            </Button>
          </Link>
        </div>
      </div>
      <div className="px-4 py-2">
        <h3 className="mb-2 px-2 text-lg font-semibold tracking-tight">Tasks</h3>
      </div>
      <ScrollArea className="flex-grow px-4">
        {!isLoading && sortedTasks.length === 0 ? (
          <div className="py-4 text-center text-muted-foreground">No tasks yet</div>
        ) : (
          sortedTasks.map(task => {
            const isSelected = selectedTask && selectedTask.id === task.id;
            const {icon: StatusIcon, color} =
              task.status && statusIcons[task.status]
                ? statusIcons[task.status]
                : {
                    icon: Circle,
                    color: 'text-gray-500',
                  };

            return (
              <Link
                key={task.id}
                href={`/tasks/${task.id}`}
                className={`mb-1 flex w-full items-center rounded-md p-2 text-left ${
                  isSelected ? 'bg-muted' : 'hover:bg-muted'
                }`}
                onClick={() => setSelectedTask(task)}
              >
                {taskMessages[task.id] && (
                  <div className="flex w-full animate-fade-in-right items-center">
                    <StatusIcon className={`mr-2 h-5 w-5 ${color}`} />
                    <div className="flex-1 truncate">
                      <span>{taskMessages[task.id]}</span>
                    </div>
                  </div>
                )}
              </Link>
            );
          })
        )}
      </ScrollArea>
      <SidebarRail />
    </div>
  );
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${inter.className} font-sans antialiased`}
      >
        <TasksProvider>
          <SidebarProvider>
            <div className="flex h-screen w-screen bg-background">
              {/* Collapsible Sidebar - hidden on mobile, visible on larger screens */}
              <Sidebar className="hidden w-64 lg:block">
                <SidebarContent>
                  <SidebarContents />
                </SidebarContent>
              </Sidebar>

              {/* Main content area */}
              <div className="flex flex-1 flex-col overflow-hidden">
                {/* Mobile header - ONLY visible on small screens */}
                <header className="flex items-center justify-between border-b p-4 lg:hidden">
                  <Link href="/" className="flex cursor-pointer items-center space-x-2">
                    <h2 className="pl-2 text-lg font-semibold">Agentex</h2>
                  </Link>
                  <div className="flex items-center space-x-2">
                    <Link href="/">
                      <Button variant="ghost" size="icon" aria-label="New Task">
                        <PenSquare className="h-5 w-5" />
                      </Button>
                    </Link>
                    <Sheet>
                      <SheetTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label="Open Menu">
                          <Menu className="h-6 w-6" />
                        </Button>
                      </SheetTrigger>
                      <SheetContent side="left" className="w-64 p-0">
                        <SheetHeader className="hidden">
                          <SheetTitle>Sidebar</SheetTitle>
                        </SheetHeader>
                        <SidebarContents />
                      </SheetContent>
                    </Sheet>
                  </div>
                </header>

                {/* Page content - takes full height on larger screens */}
                <main className="flex-1 overflow-auto">{children}</main>
              </div>
            </div>
          </SidebarProvider>
        </TasksProvider>
      </body>
    </html>
  );
}
