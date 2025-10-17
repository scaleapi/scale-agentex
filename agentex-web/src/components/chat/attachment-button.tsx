'use client';

import {useRef, useState} from 'react';
import {Paperclip} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {toast} from '@/hooks/use-toast';
import {FileAttachment} from '@/types/taskMessages';

interface AttachmentButtonProps {
  onAttachmentChange: (
    attachments: FileAttachment[] | ((curr: FileAttachment[]) => FileAttachment[])
  ) => void;
  disabled?: boolean;
  multiple?: boolean;
  accept?: string;
  maxFileSize?: number; // In bytes
  maxFiles?: number;
  currentAttachments: FileAttachment[];
}

export function AttachmentButton({
  onAttachmentChange,
  disabled = false,
  multiple = true,
  accept = '*',
  maxFileSize = 50 * 1024 * 1024, // 50MB default
  maxFiles = 10,
  currentAttachments,
}: AttachmentButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Check if adding these files would exceed the maximum
    if (currentAttachments.length + files.length > maxFiles) {
      toast({
        title: 'Too many files',
        description: `You can upload a maximum of ${maxFiles} files`,
        variant: 'destructive',
      });
      return;
    }

    // Create temporary attachment objects and update state immediately
    const newAttachments: FileAttachment[] = Array.from(files).map(file => ({
      file_id: `temp-${Date.now()}-${file.name}-${Math.random().toString(36).substring(2, 9)}`, // Add random suffix to ensure uniqueness
      name: file.name,
      status: 'uploading',
      progress: 0,
      size: file.size,
      type: file.type,
    }));

    // Add all new attachments to the current list
    const initialAttachments = [...currentAttachments, ...newAttachments];
    onAttachmentChange(initialAttachments);

    setIsUploading(true);
    console.log(`Starting upload of ${files.length} files`);

    try {
      // Process each file one at a time instead of in parallel
      for (let index = 0; index < files.length; index++) {
        const file = files[index];
        const tempAttachment = newAttachments[index];

        // Check file size
        if (file.size > maxFileSize) {
          // Update this specific attachment with an error
          const errorAttachment = {
            ...tempAttachment,
            status: 'error' as const,
            error: `File exceeds maximum size of ${Math.round(maxFileSize / (1024 * 1024))}MB`,
          };

          // Get the latest state before updating
          onAttachmentChange((currAttachments: FileAttachment[]) => {
            return currAttachments.map((att: FileAttachment) =>
              att.file_id === tempAttachment.file_id ? errorAttachment : att
            );
          });

          continue;
        }

        try {
          // Create a FormData object for the file
          const formData = new FormData();
          formData.append('file', file);

          // Upload the file
          const response = await fetch('/api/files/upload', {
            method: 'POST',
            body: formData,
          });

          if (!response.ok) {
            throw new Error(`Upload failed: ${response.statusText}`);
          }

          const data = await response.json();
          console.log(
            `File ${index + 1}/${files.length} uploaded successfully:`,
            data.id
          );

          // Update this specific attachment with success status and the real file_id
          const successAttachment = {
            ...tempAttachment,
            status: 'success' as const,
            file_id: data.id,
            progress: 100,
          };

          // Use a callback to ensure we're working with the latest state
          onAttachmentChange((currAttachments: FileAttachment[]) => {
            return currAttachments.map((att: FileAttachment) =>
              att.file_id === tempAttachment.file_id ? successAttachment : att
            );
          });
        } catch (error) {
          console.error(`Error uploading file ${index + 1}/${files.length}:`, error);

          // Update this specific attachment with error status
          const errorAttachment = {
            ...tempAttachment,
            status: 'error' as const,
            error: error instanceof Error ? error.message : 'Upload failed',
          };

          // Use a callback to ensure we're working with the latest state
          onAttachmentChange((currAttachments: FileAttachment[]) => {
            return currAttachments.map((att: FileAttachment) =>
              att.file_id === tempAttachment.file_id ? errorAttachment : att
            );
          });
        }
      }
    } finally {
      setIsUploading(false);
      console.log('All uploads completed');

      // Reset the file input
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    }
  };

  const handleClick = () => {
    if (!disabled && inputRef.current) {
      inputRef.current.click();
    }
  };

  return (
    <>
      <input
        type="file"
        ref={inputRef}
        onChange={handleFileInputChange}
        style={{display: 'none'}}
        multiple={multiple}
        accept={accept}
        disabled={disabled || isUploading}
      />
      <Button
        type="button"
        size="icon"
        variant="ghost"
        onClick={handleClick}
        disabled={disabled || isUploading}
        className="h-8 w-8 rounded-full bg-transparent hover:bg-gray-100 dark:hover:bg-gray-800"
        aria-label="Attach files"
      >
        <Paperclip className="h-4 w-4" />
      </Button>
    </>
  );
}
