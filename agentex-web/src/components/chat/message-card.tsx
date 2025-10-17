import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Card, CardContent} from '@/components/ui/card';
import {FileAttachment} from '@/types/taskMessages';
import {motion} from 'framer-motion';
import {ExternalLink, FileIcon} from 'lucide-react';
import {useEffect, useState} from 'react';
import MarkdownEditor from '../editor/markdown-editor';
import {AttachmentPreviewDialog} from './attachment-preview-dialog';

export interface MessageCardProps {
  content: string;
  style?: 'static' | 'active';
  role: 'user' | 'agent';
  attachments?: FileAttachment[];
  isIncomplete?: boolean;
}

function MessageCard({
  content,
  role,
  style,
  attachments,
  isIncomplete,
}: MessageCardProps) {
  const [previewFile, setPreviewFile] = useState<{
    id: string;
    name: string;
    type: string;
    file_id?: string;
  } | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  // Make the card visible immediately when it receives content
  useEffect(() => {
    if (content) {
      setIsVisible(true);
    }
  }, [content]);

  // Don't render anything if there's no content and not loading
  if (!content && !isIncomplete) return null;

  const handleAttachmentClick = (attachment: FileAttachment) => {
    if (attachment.status === 'success' && attachment.file_id) {
      // Open directly in browser
      window.open(`/api/file/${attachment.file_id}`, '_blank');
    }
  };

  const handleShowOptions = (e: React.MouseEvent, attachment: FileAttachment) => {
    e.stopPropagation(); // Prevent opening in new tab

    if (attachment.status === 'success' && attachment.file_id) {
      setPreviewFile({
        id: attachment.file_id,
        name: attachment.name,
        type: attachment.type,
        file_id: attachment.file_id,
      });
    }
  };

  return (
    <motion.div
      initial={{opacity: 0, y: 10}}
      animate={{opacity: isVisible ? 1 : 0, y: isVisible ? 0 : -20}}
      transition={{duration: 0.8, ease: 'easeInOut'}}
      className="relative flex"
    >
      <Card
        className={`w-full max-w-full overflow-hidden rounded-md text-gray-800 ${role === 'user' ? 'bg-gray-100' : 'bg-white'} border-gray-200 shadow-none`}
      >
        {style === 'active' && (
          <div className="h-1 animate-pulse bg-gradient-to-r from-blue-400 via-teal-500 to-purple-500"></div>
        )}
        <div className="flex flex-col justify-between p-6">
          <Badge variant="outline" className="mb-4 flex w-fit items-center gap-1 text-sm">
            {role === 'user' ? 'User' : 'Agent'}
          </Badge>
          <CardContent className="p-0">
            {isIncomplete ? (
              <>
                <pre className="whitespace-pre-wrap">{content}</pre>
                <div className="flex items-center justify-center py-4">
                  <span className="mr-2">Manifesting</span>
                  <span className="h-5 w-5 animate-spin rounded-full border-b-2 border-gray-900" />
                </div>
              </>
            ) : (
              <MarkdownEditor readOnly markdown={content} className="!p-0" />
            )}
            {attachments && attachments.length > 0 && (
              <div className="mt-4">
                {attachments.map(attachment => (
                  <div
                    key={attachment.file_id}
                    className="mb-2 flex cursor-pointer items-center justify-between rounded-md border bg-gray-50 p-2 hover:bg-gray-100"
                    onClick={() => handleAttachmentClick(attachment)}
                  >
                    <div className="flex items-center space-x-2 overflow-hidden">
                      <FileIcon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                      <div className="flex-1">
                        <p className="truncate text-sm font-medium">{attachment.name}</p>
                        <p className="text-xs text-gray-500">
                          {formatFileSize(attachment.size)} • Click to open
                        </p>
                      </div>
                    </div>
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
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </div>
      </Card>

      {/* File options dialog */}
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
    </motion.div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export default MessageCard;
