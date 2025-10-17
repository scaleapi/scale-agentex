'use client';

import {Button} from '@/components/ui/button';
import {Textarea} from '@/components/ui/textarea';
import {useTasks} from '@/context/TasksContext';
import {useToast} from '@/hooks/use-toast';
import {ALLOWED_FILE_TYPES, fileService} from '@/services';
import AgentexSDK from 'agentex';
import {agentRPCNonStreaming} from 'agentex/lib/agent-rpc-non-streaming.mjs';
import {Agent, AgentListResponse, TextContent} from 'agentex/resources';
import {Loader2, Paperclip, Send, X} from 'lucide-react';
import {useRouter} from 'next/navigation';
import {useEffect, useRef, useState} from 'react';

const BASE_URL = process.env.AGENTEX_BASE_URL || 'http://localhost:5003';

const client = new AgentexSDK({
  baseURL: BASE_URL,
  apiKey: '...',
});

export default function ComposePage() {
  const router = useRouter();
  const {toast} = useToast();
  const {refreshTasks, setPendingMessage} = useTasks();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isUploadingFiles, setIsUploadingFiles] = useState(false);
  const [attachments, setAttachments] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);

  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const agents: AgentListResponse = await client.agents.list();

        const readyAgents = agents.filter(
          agent => agent.status?.toLowerCase() === 'ready'
        );
        setAgents(readyAgents);

        // Set the first agent as active if available
        if (readyAgents.length > 0) {
          setActiveAgentId(readyAgents[0].id);
        }
      } catch (error) {
        console.error('Error fetching agents:', error);
      }
    };

    fetchAgents();
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // If Enter is pressed without Shift key
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault(); // Prevent default behavior (new line)

      // Only submit if there's content or attachments
      if (input.trim() || attachments.length > 0) {
        handleFormSubmit(e as unknown as React.FormEvent);
      }
    }
    // If Shift+Enter is pressed, let the default behavior happen (new line)
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      // Convert FileList to array
      const newFiles = Array.from(e.target.files);

      // Use fileService to validate files
      const {validFiles, invalidCount, invalidReasons} =
        fileService.validateFiles(newFiles);

      if (invalidCount > 0) {
        // Log warning messages
        console.warn(`${invalidCount} files were not valid and will not be uploaded.`);
        invalidReasons.forEach(reason => console.warn(reason));
      }

      // Add valid files to attachments
      setAttachments(prev => [...prev, ...validFiles]);

      // Reset the input to allow selecting the same file again
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const removeAttachment = (index: number) => {
    setAttachments(attachments.filter((_, i) => i !== index));
  };

  const triggerFileInput = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    if (!activeAgentId) {
      toast({
        title: 'Error',
        description: 'Please select an agent to submit a task to.',
        variant: 'destructive',
      });
      return;
    }

    e.preventDefault();

    if (!input.trim() && attachments.length === 0) return;

    // Show loading state
    setIsLoading(true);

    try {
      let message: TextContent;

      // If we have attachments, upload them and create a TextMessage
      if (attachments.length > 0) {
        setIsUploadingFiles(true);

        // Upload the files using fileService
        const {attachments: uploadedAttachments, failedCount} =
          await fileService.uploadFiles(attachments);

        if (failedCount > 0) {
          console.warn(`${failedCount} files failed to upload.`);
        }

        // Create a text message with attachments
        message = {
          type: 'text',
          author: 'user',
          style: 'static',
          content: input || 'Attached files for analysis',
          format: 'plain',
          attachments: uploadedAttachments,
        };
      } else {
        // No attachments, create a text message
        message = {
          type: 'text',
          author: 'user',
          style: 'static',
          content: input,
          format: 'plain',
          attachments: null,
        };
      }

      // Create the task first (without sending the message)
      const response = await agentRPCNonStreaming(
        client,
        {agentID: activeAgentId},
        'task/create',
        {}
      );

      // Check for errors
      if ('error' in response) {
        throw new Error(response.error.message || 'Failed to create task');
      }

      // Store the message in context to be sent by the task page
      setPendingMessage({
        content: message,
        agentId: activeAgentId,
        taskId: response.result.id,
      });

      // Refresh the tasks list to show the new task immediately
      await refreshTasks();

      // Navigate to the task page - the task page will handle sending the message
      router.push(`/tasks/${response.result.id}?agentId=${activeAgentId}`);
    } catch (error) {
      console.error('Error processing message:', error);
      toast({
        title: 'Error',
        description:
          error instanceof Error
            ? error.message
            : 'Failed to process message. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
      setIsUploadingFiles(false);
      setInput('');
      setAttachments([]);
    }
  };

  return (
    <div className="h-full flex-1 overflow-y-auto p-4">
      <div className="flex min-h-full animate-fade-in-down flex-col items-center justify-center opacity-0 [animation-delay:1s] [animation-fill-mode:forwards]">
        <h3 className="mb-2 text-center text-2xl font-semibold">Create a New Task</h3>
        <p className="mb-4 text-center text-muted-foreground">
          Select an agent to submit a task to.
        </p>
        <div className="mb-6 grid max-w-2xl grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {agents.map(agent => (
            <Button
              key={agent.id}
              variant={activeAgentId === agent.id ? 'default' : 'outline'}
              className={`h-auto w-full px-3 py-2 text-sm ${
                activeAgentId === agent.id ? 'bg-primary text-primary-foreground' : ''
              }`}
              onClick={() => setActiveAgentId(agent.id)}
            >
              <div className="flex flex-col items-start break-all text-left">
                <span className="font-medium">{agent.name}</span>
              </div>
            </Button>
          ))}
        </div>
        {activeAgentId && (
          <div className="w-full max-w-2xl">
            <form
              onSubmit={handleFormSubmit}
              className="relative rounded-3xl border border-gray-200 bg-white p-6 shadow-lg"
            >
              <Textarea
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="What would you like me to help you with?"
                className="min-h-[120px] resize-none border-0 p-2 text-lg shadow-none focus:outline-none focus:ring-0 focus-visible:ring-0"
                disabled={isLoading || isUploadingFiles}
              />

              {attachments.length > 0 && (
                <div className="mb-3 mt-2 flex flex-wrap gap-2 px-2">
                  {attachments.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm"
                    >
                      <span className="max-w-[150px] truncate">{file.name}</span>
                      <button
                        type="button"
                        onClick={() => removeAttachment(index)}
                        className="ml-2 text-gray-500 hover:text-gray-700"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center justify-between pt-4">
                <div className="flex space-x-2">
                  <button
                    type="button"
                    className="rounded-full p-3 transition-colors hover:bg-gray-100"
                    onClick={triggerFileInput}
                    disabled={isLoading || isUploadingFiles}
                  >
                    <Paperclip className="h-5 w-5 text-gray-600" />
                  </button>

                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    className="hidden"
                    multiple
                    accept={ALLOWED_FILE_TYPES.join(',')}
                  />
                </div>

                <button
                  type="submit"
                  disabled={
                    isLoading ||
                    isUploadingFiles ||
                    (!input.trim() && attachments.length === 0)
                  }
                  className="flex items-center gap-2 rounded-full bg-black px-6 py-3 text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isLoading || isUploadingFiles ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      <span>Processing...</span>
                    </>
                  ) : (
                    <>
                      <Send className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
