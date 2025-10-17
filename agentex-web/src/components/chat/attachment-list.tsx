'use client';

import {Button} from '@/components/ui/button';
import {Progress} from '@/components/ui/progress';
import {cn} from '@/lib/utils';
import {FileAttachment} from '@/types/taskMessages';
import {AlertCircle, ExternalLink, FileIcon, Loader2, X} from 'lucide-react';
import {useState} from 'react';
import {AttachmentPreviewDialog} from './attachment-preview-dialog';

interface AttachmentListProps {
  attachments: FileAttachment[];
  onRemove: (file_id: string) => void;
  readOnly?: boolean;
}

export function AttachmentList({
  attachments,
  onRemove,
  readOnly = false,
}: AttachmentListProps) {
  const [previewFile, setPreviewFile] = useState<{
    file_id: string;
    name: string;
    type: string;
  } | null>(null);

  if (!attachments || attachments.length === 0) {
    return null;
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  const handleAttachmentClick = (attachment: FileAttachment) => {
    // Only allow previewing successfully uploaded files
    if (attachment.status === 'success' && attachment.file_id) {
      // Open file directly in a new browser tab
      window.open(`/api/file/${attachment.file_id}`, '_blank');
    }
  };

  const handleShowOptions = (e: React.MouseEvent, attachment: FileAttachment) => {
    e.stopPropagation(); // Prevent opening in new tab

    // Only show options for successfully uploaded files
    if (attachment.status === 'success' && attachment.file_id) {
      setPreviewFile({
        file_id: attachment.file_id,
        name: attachment.name,
        type: attachment.type,
      });
    }
  };

  return (
    <div className="w-full space-y-2 px-2 py-1">
      {attachments.map(attachment => (
        <div
          key={attachment.file_id}
          className={cn(
            'flex items-center justify-between rounded-md border bg-background p-2',
            attachment.status === 'error' &&
              'border-red-500 bg-red-50 dark:bg-red-950/20',
            attachment.status === 'success' && 'cursor-pointer hover:bg-gray-50'
          )}
          onClick={() =>
            attachment.status === 'success' && handleAttachmentClick(attachment)
          }
        >
          <div className="flex items-center space-x-2 overflow-hidden">
            <FileIcon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{attachment.name}</p>
              <div className="flex items-center text-xs text-muted-foreground">
                {formatFileSize(attachment.size)}
                {attachment.status === 'error' && (
                  <span className="ml-2 flex items-center text-red-600">
                    <AlertCircle className="mr-1 h-3 w-3" />
                    {attachment.error || 'Upload failed'}
                  </span>
                )}
                {attachment.status === 'uploading' && (
                  <span className="ml-2 flex items-center text-amber-600">
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    Uploading...
                  </span>
                )}
                {attachment.status === 'success' && (
                  <span className="ml-2 text-gray-500">(Click to open)</span>
                )}
              </div>
              {attachment.status === 'uploading' && (
                <Progress value={attachment.progress || 0} className="mt-1 h-1" />
              )}
            </div>
          </div>
          <div className="flex items-center">
            {!readOnly && attachment.status === 'success' && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded-full"
                onClick={e => handleShowOptions(e, attachment)}
                aria-label="Show download options"
              >
                <ExternalLink className="h-3 w-3" />
              </Button>
            )}
            {!readOnly && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded-full"
                onClick={e => {
                  e.stopPropagation(); // Prevent click from bubbling to parent
                  onRemove(attachment.file_id);
                }}
                aria-label="Remove attachment"
              >
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>
        </div>
      ))}

      {/* File Preview Dialog (now just options) */}
      {previewFile && previewFile.file_id && (
        <AttachmentPreviewDialog
          name={previewFile.name}
          contentType={previewFile.type}
          isOpen={!!previewFile}
          onOpenChange={open => {
            if (!open) setPreviewFile(null);
          }}
          onOpenInBrowser={() => {
            // TODO: make this better
            window.open(`/api/file/${previewFile.file_id}`, '_blank');
            setPreviewFile(null); // Close the dialog after opening
          }}
          onDownload={() => {
            // TODO: make this better
            const a = document.createElement('a');
            a.href = `/api/file/${previewFile.file_id}`;
            a.download = previewFile.name; // This will prompt download instead of opening
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setPreviewFile(null); // Close the dialog after download starts
          }}
        />
      )}
    </div>
  );
}
