'use client';

import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {FileAttachment} from '@/types/taskMessages';
import type {Agent} from 'agentex/resources';
import {Ellipsis, Loader2, Send, X} from 'lucide-react';
import {useState} from 'react';
import {AttachmentButton} from './attachment-button';
import {AttachmentList} from './attachment-list';
import {FilePicker} from './file-picker';

interface TaskControlsProps {
  userInput: string;
  setUserInput: (value: string) => void;
  handleSubmit: (e: React.FormEvent) => void;
  isThinking: boolean;
  taskInTerminalState: boolean;
  isApproving: boolean;
  handleCancelTask: () => void;
  isCancelling: boolean;
  onAttachmentsChange?: (
    attachments: FileAttachment[] | ((curr: FileAttachment[]) => FileAttachment[])
  ) => void;
  agents: Agent[];
  activeAgentId: string | null;
  onAgentChange: (agentId: string) => void;
}

const TaskControls: React.FC<TaskControlsProps> = ({
  userInput,
  setUserInput,
  handleSubmit,
  isThinking,
  taskInTerminalState,
  handleCancelTask,
  isCancelling,
  onAttachmentsChange,
  agents,
  activeAgentId,
  onAgentChange,
}) => {
  const [attachments, setAttachments] = useState<FileAttachment[]>([]);

  // Custom submit handler to check if all attachments are uploaded
  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Check if there are any attachments still uploading
    const hasUploadingAttachments = attachments.some(
      attachment => attachment.status === 'uploading'
    );

    if (hasUploadingAttachments) {
      // Prevent submission if files are still uploading
      alert('Please wait for all attachments to finish uploading');
      return;
    }

    // Get all successfully uploaded attachments
    const successfulAttachments = attachments.filter(
      attachment => attachment.status === 'success' && attachment.file_id
    );

    // Attach the successful attachments to the event object
    (e as unknown as {attachments: FileAttachment[]}).attachments = successfulAttachments;

    // Also forward the attachments through the callback for redundancy
    if (onAttachmentsChange) {
      onAttachmentsChange(successfulAttachments);
    }

    // Call the parent's submit handler with our modified event
    handleSubmit(e);

    // Clear attachments after submission
    setAttachments([]);
  };

  // Handle attachment updates
  const handleAttachmentChange = (
    newAttachments: FileAttachment[] | ((curr: FileAttachment[]) => FileAttachment[])
  ) => {
    // Update local state
    if (typeof newAttachments === 'function') {
      setAttachments(prev => {
        const updatedAttachments = newAttachments(prev);
        // Forward to parent component if available
        if (onAttachmentsChange) {
          onAttachmentsChange(updatedAttachments);
        }
        return updatedAttachments;
      });
    } else {
      setAttachments(newAttachments);
      // Forward to parent component if available
      if (onAttachmentsChange) {
        onAttachmentsChange(newAttachments);
      }
    }
  };

  // Handle attachment removal
  const handleRemoveAttachment = (id: string) => {
    setAttachments(prev => {
      const filtered = prev.filter(attachment => attachment.file_id !== id);
      // Also notify parent of removal
      if (onAttachmentsChange) {
        onAttachmentsChange(filtered);
      }
      return filtered;
    });
  };

  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-4">
      {attachments.length > 0 && (
        <div className="mb-2">
          <AttachmentList attachments={attachments} onRemove={handleRemoveAttachment} />
        </div>
      )}
      <form onSubmit={onSubmit} className="mb-6 w-full">
        <div className="flex w-full">
          <div className="flex flex-grow flex-col overflow-hidden rounded-md border bg-white">
            <div className="flex items-center border-b bg-gray-50 px-4 py-2">
              <Select
                value={activeAgentId || ''}
                onValueChange={onAgentChange}
                disabled={taskInTerminalState || isThinking}
              >
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Select an agent" />
                </SelectTrigger>
                <SelectContent>
                  {agents.map(agent => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Input
              type="text"
              placeholder="Provide new instructions..."
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
              className="min-h-[52px] flex-grow rounded-t-md border-0 px-4 py-4 text-base placeholder:font-light placeholder:text-gray-400 placeholder:opacity-70 focus-visible:ring-0 focus-visible:ring-offset-0"
              disabled={taskInTerminalState || isThinking}
            />
            <div className="flex items-center border-t bg-gray-50 px-3 py-2">
              <div className="flex items-center space-x-3">
                <FilePicker
                  onFileSelect={handleAttachmentChange}
                  currentAttachments={attachments}
                  disabled={taskInTerminalState || isThinking}
                />
                <AttachmentButton
                  onAttachmentChange={handleAttachmentChange}
                  disabled={taskInTerminalState || isThinking}
                  currentAttachments={attachments}
                />
              </div>
              <div className="ml-auto flex space-x-2">
                <Button
                  type="submit"
                  size="icon"
                  variant="ghost"
                  className="h-9 w-9 rounded-full text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  disabled={taskInTerminalState || isThinking}
                >
                  {isThinking ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  <span className="sr-only">Send</span>
                </Button>
                <Button
                  size="sm"
                  className="bg-red-500 hover:bg-red-600"
                  onClick={handleCancelTask}
                  disabled={taskInTerminalState || isCancelling}
                >
                  {isCancelling ? (
                    <Ellipsis className="mr-2 h-4 w-4 animate-pulse" />
                  ) : (
                    <>
                      <X className="mr-2 h-4 w-4" />
                      <span>Cancel</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
};

export default TaskControls;
