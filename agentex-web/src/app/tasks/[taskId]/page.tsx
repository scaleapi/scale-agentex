'use client';

import MessageCard from '@/components/chat/message-card';
import TaskBadges from '@/components/chat/task-badges';
import TaskControls from '@/components/chat/task-controls';
import {ToolMessageCard} from '@/components/kit/tool-message-card';
import {Button} from '@/components/ui/button';
import {ResizablePanel, ResizablePanelGroup} from '@/components/ui/resizable';
import {useTasks} from '@/context/TasksContext';
import {useToast} from '@/hooks/use-toast';
import {
  CompletionCallback,
  ConnectionCallback,
  ErrorCallback,
  StreamUpdateCallback,
} from '@/types/taskMessageUpdates';
import {D, G, pipe} from '@mobily/ts-belt';
import AgentexSDK from 'agentex';
import {
  agenticTaskEventGenerator,
  agentRPCNonStreaming,
  agentRPCWithStreaming,
  aggregateMessageEvents,
} from 'agentex/lib/index';
import {TaskStreamErrorEvent, TaskStreamEvent} from 'agentex/lib/schemas/task-stream';
import type {Agent, TaskMessage, TaskMessageDelta, TextContent} from 'agentex/resources';
import {AnimatePresence, motion} from 'framer-motion';
import {ArrowDown} from 'lucide-react';
import {useRouter, useSearchParams} from 'next/navigation';
import {use, useCallback, useEffect, useRef, useState} from 'react';

const BASE_URL = process.env.AGENTEX_BASE_URL || 'http://localhost:5003';

const client = new AgentexSDK({baseURL: BASE_URL, apiKey: 'dummy'});

/**
 * converts an ISO timestamp into a date object, but defaults to UTC when there's no timezone info
 */
const normalizeTimestamp = (timestamp: string): Date => {
  // has timezone or in UTC
  if (/[+-]\d{2}:?\d{2}$|Z$/.test(timestamp)) {
    return new Date(timestamp);
  }

  // assume UTC
  return new Date(timestamp + 'Z');
};

// Helper function to handle streaming message sending
const handleSyncMessage = async (
  agentId: string,
  taskId: string,
  content: TextContent,
  setMessageEntries: React.Dispatch<React.SetStateAction<TaskMessage[]>>,
  scrollToLastUserMessage: () => void,
  taskMessagesRef: React.RefObject<TaskMessage[] | null>,
  deltasRef: React.RefObject<Map<TaskMessage['id'], TaskMessageDelta>>,
  eventBufferRef: React.RefObject<TaskStreamEvent[]>,
  signal: AbortSignal
) => {
  // Generate a temporary ID for the user message
  const currentTimestamp = new Date().toISOString();

  // Immediately add the user message to the entries
  const userMessage: TaskMessage = {
    task_id: taskId,
    created_at: currentTimestamp,
    updated_at: currentTimestamp,
    content: content,
    streaming_status: null, // Streaming status should always be null for user messages
  };

  setMessageEntries(prevEntries => [...prevEntries, userMessage]);

  // Scroll to position the user message at the top after adding it
  await new Promise<void>(resolve => {
    setTimeout(() => {
      scrollToLastUserMessage();
      resolve();
    }, 0);
  });

  for await (const response of agentRPCWithStreaming(
    client,
    {agentID: agentId},
    'message/send',
    {task_id: taskId, content},
    {signal}
  )) {
    if ('error' in response) {
      console.error('Error sending message:', response.error);
      throw new Error(response.error.message || 'Failed to send message');
    }

    if (taskMessagesRef.current === null) {
      // Buffer events until task messages are loaded
      eventBufferRef.current.push(response.result);
      continue;
    }

    // update refs all at once
    [taskMessagesRef.current, deltasRef.current] = aggregateMessageEvents(
      taskMessagesRef.current,
      deltasRef.current,
      [...eventBufferRef.current, response.result]
    );
    eventBufferRef.current = [];

    // update state
    const updatedTaskMessages = taskMessagesRef.current;
    setMessageEntries(prevEntries => {
      // Keep any temporary messages (IDs starting with TEMP_MESSAGE_ID_PREFIX)
      const existingTempMessages = prevEntries.filter(message => message.id == null);

      return [...existingTempMessages, ...updatedTaskMessages];
    });
  }

  const refreshedMessages = await client.messages.list({task_id: taskId}, {signal});
  setMessageEntries(refreshedMessages);
};

// Helper function to handle agentic message sending (uses existing SSE stream)
const handleAgenticMessage = async (
  agentId: string,
  taskId: string,
  content: TextContent,
  scrollToLastUserMessage: () => void
) => {
  try {
    // For agentic mode, we send an event with the message
    await agentRPCNonStreaming(client, {agentID: agentId}, 'event/send', {
      task_id: taskId,
      content,
    });

    // Scroll to position the user message at the top after adding it
    setTimeout(() => {
      scrollToLastUserMessage();
    }, 150);
  } catch (err) {
    console.error('Error sending agentic message:', err);
    throw err;
  }
};

const Page = ({params}: {params: Promise<{taskId: string}>}) => {
  const {taskId} = use(params);
  const {toast} = useToast();
  const {selectedTask, setSelectedTask, pendingMessage, clearPendingMessage} = useTasks();
  const router = useRouter();
  const searchParams = useSearchParams();
  const agentIdFromQuery = searchParams.get('agentId');

  // TODO: switch to zustand so we don't need to duplicate this stuff
  const [messageEntries, setMessageEntries] = useState<TaskMessage[]>([]);
  const taskMessagesRef = useRef<TaskMessage[] | null>(null);
  // Map to track deltas per message
  const deltasRef = useRef<Map<TaskMessage['id'], TaskMessageDelta>>(new Map());
  // used to buffer events before task messages are loaded
  const eventBufferRef = useRef<TaskStreamEvent[]>([]);

  // State variables
  const [isLoading, setIsLoading] = useState(true);
  const [isThinking, setIsThinking] = useState(false);
  const [userInput, setUserInput] = useState<string>('');
  const [isCancelling, setIsCancelling] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(agentIdFromQuery);
  const selectedAgent = agents.find(agent => agent.id === activeAgentId);
  const previousMessagesLength = useRef<number>(0);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const newestMessageRef = useRef<HTMLDivElement>(null);

  // Use a ref to store the latest attachments and avoid race conditions with state updates
  const latestAttachmentsRef = useRef<TextContent.Attachment[]>([]);

  // Ref for the end of messages container for scrolling
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [pendingAttachments, setPendingAttachments] = useState<TextContent.Attachment[]>(
    []
  );

  // Add a ref for the last user message
  const lastUserMessageRef = useRef<HTMLDivElement>(null);

  // Track processed pending messages to prevent double sending
  const processedPendingMessageRef = useRef<boolean>(false);

  // used since all these async functions have no clue if they're current or not
  // TODO: fix everything
  const [pageAbortController] = useState(new AbortController());
  useEffect(() => {
    () => {
      pageAbortController.abort();
    };
  }, [pageAbortController, taskId]);

  // Add a new style for the last user message element
  const lastUserMessageStyle = {
    scrollMarginTop: '16px', // Same as the padding between cards
  };

  // Function to scroll to the last user message
  const scrollToLastUserMessage = useCallback(() => {
    if (lastUserMessageRef.current && messagesContainerRef.current) {
      // Calculate the exact position to scroll the user message to the top with 16px padding
      const containerRect = messagesContainerRef.current.getBoundingClientRect();
      const messageRect = lastUserMessageRef.current.getBoundingClientRect();
      const currentScrollTop = messagesContainerRef.current.scrollTop;

      // Calculate the target scroll position to place the message at the top with 16px padding
      const targetScrollTop = currentScrollTop + messageRect.top - containerRect.top - 16;

      messagesContainerRef.current.scrollTo({
        top: targetScrollTop,
        behavior: 'smooth',
      });
    } else {
      // Fallback to bottom if no user message is found
      messagesEndRef.current?.scrollIntoView({behavior: 'smooth'});
    }
  }, []);

  // Function to poll for task status updates after taking an action
  const pollTaskStatus = useCallback(
    async (taskId: string, signal: AbortSignal, attempts = 5, delay = 1000) => {
      // Initial delay before first poll
      await new Promise(resolve => setTimeout(resolve, delay));

      for (let i = 0; i < attempts && !signal.aborted; i++) {
        try {
          console.log(`Polling task status attempt ${i + 1} of ${attempts}`);
          const fetchedTask = await client.tasks.retrieve(taskId, {signal});
          setSelectedTask(fetchedTask);

          // If task is in a terminal state, stop polling
          if (fetchedTask.status != null && fetchedTask.status !== 'RUNNING') {
            break;
          }
        } catch (error) {
          if (signal.aborted) {
            return;
          }
          console.error('Error polling task status:', error);
        }
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    },
    [setSelectedTask]
  );

  // Load messages when taskId changes
  useEffect(() => {
    let current = true;

    (async () => {
      if (!taskId) {
        console.log('No taskId provided, skipping message loading');
        return;
      }
      setIsLoading(true);
      try {
        const data = await client.messages.list({task_id: taskId});

        if (!current) {
          return;
        }

        if (data.length === 0) {
          console.warn('No messages found for task during initial load:', taskId);
        }

        // update refs all at once
        [taskMessagesRef.current, deltasRef.current] = aggregateMessageEvents(
          data,
          new Map(),
          eventBufferRef.current
        );
        eventBufferRef.current = [];

        // update state
        const updatedTaskMessages = taskMessagesRef.current;
        setMessageEntries(updatedTaskMessages);

        // After messages are loaded, scroll to last user message
        setTimeout(() => {
          if (current) {
            scrollToLastUserMessage();
          }
        }, 0);
      } catch (error) {
        console.error('Error loading messages:', error);
        toast({
          title: 'Error',
          description: 'Failed to load messages. Please try again.',
          variant: 'destructive',
        });
      } finally {
        setIsLoading(false);
      }
    })();

    return () => {
      current = false;
    };
  }, [taskId, toast, scrollToLastUserMessage]);

  // Load task data
  useEffect(() => {
    if (!taskId) return;

    let current = true;

    (async () => {
      try {
        const response = await client.tasks.retrieve(taskId);

        if (!current) {
          return;
        }

        const taskData = response;
        setSelectedTask(taskData);
      } catch (error) {
        console.error('Error loading task data:', error);
      }
    })();

    return () => {
      current = false;
    };
  }, [taskId, setSelectedTask]);

  // Function to scroll to the bottom of messages
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({behavior: 'smooth'});
  }, []);

  // Function to scroll so that the newest message is at the top of the viewport
  const scrollToNewMessage = useCallback(() => {
    if (newestMessageRef.current && messagesContainerRef.current) {
      const offsetTop = newestMessageRef.current.offsetTop;

      // Scroll to position the newest message at the top of the viewport with some padding
      messagesContainerRef.current.scrollTo({
        top: offsetTop - 20, // 20px padding from the top
        behavior: 'smooth',
      });
    } else {
      console.warn('Cannot scroll to new message - refs not available');
    }
  }, []);

  // Updated scroll behavior when new messages are added
  useEffect(() => {
    const currentMessagesCount = Object.keys(messageEntries).length;

    // Only scroll if messages length actually increased and autoscroll is enabled
    if (currentMessagesCount > previousMessagesLength.current && autoScrollEnabled) {
      // Find if the newest message is from the agent
      const messagesArray = Object.values(messageEntries);
      if (messagesArray.length > 0) {
        const newestMessage = messagesArray[messagesArray.length - 1];
        if (newestMessage.content.author === 'agent') {
          // Use the new scrolling behavior for agent messages
          setTimeout(scrollToNewMessage, 100); // Small delay to ensure the DOM is updated
        }
      }
    }

    // Always update the previous length even if we don't scroll
    previousMessagesLength.current = currentMessagesCount;
  }, [scrollToNewMessage, autoScrollEnabled, messageEntries]);

  // Load available agents
  useEffect(() => {
    let current = true;

    (async () => {
      try {
        // Only fetch agents for this specific task
        const availableAgents = await client.agents.list({task_id: taskId});

        if (!current) {
          return;
        }

        const readyAgents = availableAgents.filter(agent => agent.status === 'Ready');
        setAgents(readyAgents);

        // If no agent is selected and we have agents, select the first one
        if (!activeAgentId && readyAgents.length > 0) {
          setActiveAgentId(readyAgents[0].id);
          // Update URL with the selected agent
          router.replace(`/tasks/${taskId}?agentId=${readyAgents[0].id}`);
        }
      } catch (error) {
        console.error('Error loading agents:', error);
        toast({
          title: 'Error',
          description: 'Failed to load available agents',
          variant: 'destructive',
        });
      }
    })();

    return () => {
      current = false;
    };
  }, [taskId, activeAgentId, router, toast]);

  // Handle agent change
  const handleAgentChange = (newAgentId: string) => {
    setActiveAgentId(newAgentId);
    // Update URL with the new agent ID
    router.replace(`/tasks/${taskId}?agentId=${newAgentId}`);
  };

  // Render messages

  const displayTaskMessages: TaskMessage[] = Object.values(messageEntries).sort(
    (a, b) => {
      if (b.created_at == null) {
        return 1;
      } else if (a.created_at == null) {
        return -1;
      }

      try {
        return (
          normalizeTimestamp(a.created_at).getTime() -
          normalizeTimestamp(b.created_at).getTime()
        );
      } catch (error) {
        console.warn('Error sorting messages', error);
        return 0;
      }
    }
  );

  const lastUserMessageIndex = displayTaskMessages.findLastIndex(
    message => message.content.author === 'user'
  );

  const hasStreamingMessage = displayTaskMessages.some(
    message => message.streaming_status === 'IN_PROGRESS'
  );

  const copyTaskId = () => {
    navigator.clipboard.writeText(taskId).then(() => {
      setIsCopied(true);
      toast({
        title: 'Copied!',
        description: `Task ID ${taskId} copied to clipboard`,
      });
      setTimeout(() => setIsCopied(false), 2000);
    });
  };

  // Handle pending message from homepage - must be after connectToStream definition
  useEffect(() => {
    if (!pendingMessage || !taskId) {
      return;
    }

    // Check if this pending message is for the current task
    if (pendingMessage.taskId !== taskId) {
      return;
    }

    if (!selectedAgent) {
      return;
    }

    const abortController = new AbortController();

    (async () => {
      // we only try to send the pending message once
      // TODO: this pending message system is super hacky and unreliable
      if (processedPendingMessageRef.current) {
        return;
      }
      processedPendingMessageRef.current = true;

      try {
        setIsThinking(true);
        if (selectedAgent.acp_type === 'sync') {
          // For sync agents, use the existing handleSyncMessage
          await handleSyncMessage(
            pendingMessage.agentId,
            pendingMessage.taskId,
            pendingMessage.content,
            setMessageEntries,
            scrollToLastUserMessage,
            taskMessagesRef,
            deltasRef,
            eventBufferRef,
            abortController.signal
          );
        } else {
          // For agentic agents, use the existing handleAgenticMessage
          await handleAgenticMessage(
            pendingMessage.agentId,
            pendingMessage.taskId,
            pendingMessage.content,
            scrollToLastUserMessage
          );
        }
      } catch (error) {
        if (abortController.signal.aborted) {
          // expected abort due to cleanup
          processedPendingMessageRef.current = false;
        } else {
          console.error('Error sending pending message:', error);

          toast({
            title: 'Error',
            description:
              error instanceof Error ? error.message : 'Failed to send pending message',
            variant: 'destructive',
          });
        }
      } finally {
        // Clear the pending message after both success and error
        clearPendingMessage();
        setIsThinking(false);
      }
    })();

    return () => {
      abortController.abort();
    };
  }, [
    pendingMessage,
    taskId,
    clearPendingMessage,
    scrollToLastUserMessage,
    toast,
    selectedAgent,
  ]);

  // Only connect to stream if agent is agentic
  const shouldConnectToStream = selectedAgent?.acp_type === 'agentic';
  // Monitor SSE connection state and reconnect if needed
  useEffect(() => {
    if (!taskId || !shouldConnectToStream) {
      return;
    }

    const handleStreamEvent: StreamUpdateCallback = data => {
      if (taskMessagesRef.current === null) {
        // Buffer events until task messages are loaded
        eventBufferRef.current.push(data);
        return;
      }

      // update refs all at once
      [taskMessagesRef.current, deltasRef.current] = aggregateMessageEvents(
        taskMessagesRef.current,
        deltasRef.current,
        [...eventBufferRef.current, data]
      );
      eventBufferRef.current = [];

      // update state
      // agentic ACP shouldn't have temporary messages in the frontend
      setMessageEntries([...taskMessagesRef.current]);
    };

    const handleError: ErrorCallback = error => {
      console.error('SSE stream received an error message:', error);
      toast({
        title: 'Error',
        description: pipe(D.get(error as TaskStreamErrorEvent, 'message'), val =>
          G.isString(val) ? val : 'Error from SSE stream, but connection was not lost'
        ),
        variant: 'destructive',
      });
    };

    const handleConnected: ConnectionCallback = () => {
      console.log('SSE connection established');
    };

    const handleCompleted: CompletionCallback = taskId => {
      console.log('SSE stream completed for task:', taskId);
    };

    const abortController = new AbortController();

    const connectToStream = async (signal: AbortSignal): Promise<void> => {
      try {
        for await (const event of agenticTaskEventGenerator(
          client,
          {taskID: taskId},
          {
            signal,
          }
        )) {
          if (event.type === 'connected') {
            handleConnected();
          } else if (event.type === 'error') {
            handleError(event);
          } else {
            handleStreamEvent(event);
          }
        }
        if (!signal.aborted) {
          handleCompleted(taskId);
        }
      } catch (error) {
        if (!signal.aborted) {
          console.error('Error streaming', error);
          toast({
            title: 'Error',
            description: error instanceof Error ? error.message : 'Error streaming',
            variant: 'destructive',
          });
        }
      }
    };

    // reconnect loop
    (async () => {
      while (!abortController.signal.aborted) {
        await connectToStream(abortController.signal);

        if (!abortController.signal.aborted) {
          await new Promise(resolve => setTimeout(resolve, 3_000));
        }
      }
    })();

    return () => {
      abortController.abort();
    };
  }, [taskId, shouldConnectToStream, toast]);

  // Add effect to scroll to last user message when component mounts
  useEffect(() => {
    // Scroll to last user message when the component mounts or refreshes
    const initialScrollTimeout = setTimeout(() => {
      scrollToLastUserMessage();
    }, 500); // Small delay to ensure DOM is fully rendered

    return () => clearTimeout(initialScrollTimeout);
  }, [scrollToLastUserMessage]);

  // Update handleCancel to use activeAgentId instead of task.agent_id
  const handleCancel = async () => {
    if (!taskId || !activeAgentId) return;
    setIsCancelling(true);
    try {
      await agentRPCNonStreaming(client, {agentID: activeAgentId}, 'task/cancel', {
        task_id: taskId,
      });
      pollTaskStatus(taskId, pageAbortController.signal);
    } catch (error) {
      console.error('Error cancelling task:', error);
      toast({
        title: 'Error',
        description: 'Failed to cancel task',
        variant: 'destructive',
      });
    } finally {
      setIsCancelling(false);
    }
  };

  // Handle file attachments
  const handleAttachmentsChange = (
    attachments:
      | TextContent.Attachment[]
      | ((curr: TextContent.Attachment[]) => TextContent.Attachment[])
  ) => {
    if (typeof attachments === 'function') {
      const newAttachments = attachments(latestAttachmentsRef.current);
      setPendingAttachments(newAttachments);
      latestAttachmentsRef.current = newAttachments;
    } else {
      setPendingAttachments(attachments);
      latestAttachmentsRef.current = attachments;
    }
  };

  // After sending a message, always reload messages from backend to avoid missing user messages
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!activeAgentId) {
      toast({
        title: 'Error',
        description: 'No agent selected',
        variant: 'destructive',
      });
      return;
    }

    // Get attachments from both sources
    const eventAttachments =
      (e as {attachments?: TextContent.Attachment[] | null}).attachments ?? [];
    const refAttachments = latestAttachmentsRef.current;

    // Use eventAttachments if available, otherwise use refAttachments
    const allFileAttachments =
      eventAttachments.length > 0 ? eventAttachments : refAttachments;

    if (!userInput.trim() && allFileAttachments.length === 0) return;

    setUserInput('');
    setIsThinking(true);

    try {
      if (selectedTask?.id) {
        // Create a TaskMessage object with current timestamp
        const content: TextContent = {
          type: 'text',
          author: 'user',
          style: 'static',
          format: 'plain',
          content: userInput,
          attachments: allFileAttachments.length > 0 ? allFileAttachments : null,
        };

        // Log the final message being sent
        // console.log('Sending message to workflow:', JSON.stringify(content, null, 2));

        // Handle message based on agent type
        if (!selectedAgent) {
          toast({
            title: 'Error',
            description: 'No agent selected for this task',
            variant: 'destructive',
          });
          return;
        }

        if (selectedAgent.acp_type === 'sync') {
          // For sync agents, we wait for the response
          await handleSyncMessage(
            activeAgentId,
            selectedTask.id,
            content,
            setMessageEntries,
            scrollToLastUserMessage,
            taskMessagesRef,
            deltasRef,
            eventBufferRef,
            pageAbortController.signal
          );
        } else {
          // For agentic agents, we send an event and let the stream handle the response
          await handleAgenticMessage(
            activeAgentId,
            selectedTask.id,
            content,
            scrollToLastUserMessage
          );
        }

        // Clear pending attachments after submission
        setPendingAttachments([]);
        latestAttachmentsRef.current = [];

        // Scroll to show the user message at the top of the screen after DOM updates
        if (autoScrollEnabled) {
          setTimeout(scrollToLastUserMessage, 200);
        }
      }
    } catch (err) {
      if (!pageAbortController.signal.aborted) {
        console.error('Error in form submission:', err);
        toast({
          title: 'Error',
          description: err instanceof Error ? err.message : 'Failed to send message',
          variant: 'destructive',
        });
      }
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <ResizablePanelGroup direction="horizontal" className="h-full bg-white">
      <ResizablePanel defaultSize={100} className="h-full">
        <div className="flex h-full flex-col">
          {selectedTask && (
            <>
              <div className="flex-grow overflow-y-auto" ref={messagesContainerRef}>
                <div className="mx-auto max-w-5xl space-y-4 p-4 pt-8">
                  {isLoading ? (
                    <div className="flex h-32 items-center justify-center">
                      <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-gray-900" />
                    </div>
                  ) : (
                    <>
                      {pendingAttachments.length > 0 && (
                        <div className="mb-2 flex justify-between">
                          <div className="text-sm text-gray-500">
                            {pendingAttachments.length} file
                            {pendingAttachments.length !== 1 ? 's' : ''} pending
                            submission
                          </div>
                        </div>
                      )}
                      <AnimatePresence>
                        {displayTaskMessages.map((task_message, index) => {
                          const message = task_message.content;

                          // Add a ref to the most recent message from the agent
                          const isNewestAgentMessage =
                            index === displayTaskMessages.length - 1 &&
                            message.author === 'agent';

                          // Add ref to the last user message
                          const isLastUserMessage = index === lastUserMessageIndex;

                          if (message.type === 'tool_request') {
                            const toolRequest = message;
                            return (
                              <div
                                key={index}
                                ref={
                                  isNewestAgentMessage
                                    ? newestMessageRef
                                    : isLastUserMessage
                                      ? lastUserMessageRef
                                      : undefined
                                }
                                style={
                                  isLastUserMessage ? lastUserMessageStyle : undefined
                                }
                              >
                                <motion.div
                                  initial={{opacity: 0, y: 10}}
                                  animate={{opacity: 1, y: 0}}
                                  transition={{duration: 0.3}}
                                  className="relative flex"
                                >
                                  <ToolMessageCard
                                    variant="request"
                                    activityStatus="static"
                                    name={toolRequest.name}
                                    content={toolRequest.arguments}
                                  />
                                </motion.div>
                              </div>
                            );
                          } else if (message.type === 'tool_response') {
                            const toolResponse = message;
                            return (
                              <div
                                key={index}
                                ref={
                                  isNewestAgentMessage
                                    ? newestMessageRef
                                    : isLastUserMessage
                                      ? lastUserMessageRef
                                      : undefined
                                }
                                style={
                                  isLastUserMessage ? lastUserMessageStyle : undefined
                                }
                              >
                                <motion.div
                                  initial={{opacity: 0, y: 10}}
                                  animate={{opacity: 1, y: 0}}
                                  transition={{duration: 0.3}}
                                  className="relative flex"
                                >
                                  <ToolMessageCard
                                    variant="response"
                                    activityStatus="static"
                                    name={toolResponse.name}
                                    content={toolResponse.content}
                                  />
                                </motion.div>
                              </div>
                            );
                          }

                          let content = '';
                          let attachments: TextContent.Attachment[] | null | undefined =
                            undefined;

                          if (message.type === 'text') {
                            const textMessage = message;
                            content = textMessage.content;
                            attachments = textMessage.attachments;
                          } else if (message.type === 'data') {
                            const jsonMessage = message;
                            content = JSON.stringify(jsonMessage.data, null, 2);
                          }

                          // Render the message card, but show a spinner in place of content if incomplete
                          return (
                            <div
                              key={index}
                              ref={
                                isNewestAgentMessage
                                  ? newestMessageRef
                                  : isLastUserMessage
                                    ? lastUserMessageRef
                                    : undefined
                              }
                              style={isLastUserMessage ? lastUserMessageStyle : undefined}
                            >
                              <MessageCard
                                content={content}
                                role={message.author}
                                style="static"
                                attachments={attachments ?? undefined}
                                isIncomplete={
                                  task_message.streaming_status === 'IN_PROGRESS'
                                }
                              />
                            </div>
                          );
                        })}

                        {isThinking && !hasStreamingMessage && (
                          <div className="flex items-center justify-center py-4">
                            <span className="mr-2">Thinking</span>
                            <span className="h-5 w-5 animate-spin rounded-full border-b-2 border-gray-900" />
                          </div>
                        )}
                      </AnimatePresence>
                      {/* Add extra space at the bottom to allow room for streaming text */}
                      {/* <div className="h-[60vh]" /> */}
                      <div ref={messagesEndRef} />
                    </>
                  )}
                </div>
                <div className="pointer-events-none sticky bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-white via-white/60 to-transparent" />

                {/* Scroll to bottom button - only visible when autoscroll is disabled */}
                {!autoScrollEnabled && Object.keys(messageEntries).length > 0 && (
                  <div className="fixed bottom-28 right-8 z-10">
                    <Button
                      size="sm"
                      className="h-10 w-10 rounded-full p-3 shadow-md"
                      onClick={scrollToBottom}
                    >
                      <ArrowDown className="h-4 w-4" />
                      <span className="sr-only">Scroll to bottom</span>
                    </Button>
                  </div>
                )}
              </div>
              <div className="relative">
                {/* {pendingAttachments.length > 0 && (
                  <div className="max-w-5xl w-full mx-auto px-4 mb-2">
                    <div className="p-2 bg-yellow-50 border border-yellow-200 rounded-md">
                      <div className="flex justify-between items-center">
                        <p className="text-sm text-yellow-700 font-medium">
                          {pendingAttachments.length} file
                          {pendingAttachments.length !== 1 ? 's' : ''} will be sent with your next
                          message:
                        </p>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-yellow-700 hover:text-yellow-900 text-xs"
                          onClick={() => setPendingAttachments([])}
                        >
                          Clear All
                        </Button>
                      </div>
                      <ul className="text-xs text-yellow-600 mt-1">
                        {pendingAttachments.map(att => (
                          <li key={att.file_id}>{att.name}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )} */}
                <div className="animate-fade-in-up">
                  <TaskBadges
                    isCopied={isCopied}
                    task={selectedTask}
                    copyTaskId={copyTaskId}
                    autoScrollEnabled={autoScrollEnabled}
                    setAutoScrollEnabled={setAutoScrollEnabled}
                  />
                  <TaskControls
                    userInput={userInput}
                    setUserInput={setUserInput}
                    handleSubmit={handleSubmit}
                    isThinking={isThinking}
                    taskInTerminalState={
                      selectedTask.status != null && selectedTask.status !== 'RUNNING'
                    }
                    isApproving={isThinking}
                    handleCancelTask={handleCancel}
                    isCancelling={isCancelling}
                    onAttachmentsChange={handleAttachmentsChange}
                    agents={agents}
                    activeAgentId={activeAgentId}
                    onAgentChange={handleAgentChange}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
};

export default Page;
