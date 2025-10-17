'use client';

import {Button} from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {ScrollArea} from '@/components/ui/scroll-area';
import {FileAttachment} from '@/types/taskMessages';
import {Check, FileIcon, Folder, Loader2} from 'lucide-react';
import {useState} from 'react';

interface ScaleFile {
  id: string;
  object: string;
  filename: string;
  size: number;
  created_at: string;
  md5_checksum: string;
  mime_type: string;
}

interface FilePickerProps {
  onFileSelect: (attachments: FileAttachment[]) => void;
  disabled?: boolean;
  currentAttachments: FileAttachment[];
}

export function FilePicker({
  onFileSelect,
  disabled = false,
  currentAttachments,
}: FilePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [files, setFiles] = useState<ScaleFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<ScaleFile[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [startingAfter, setStartingAfter] = useState<string | null>(null);

  // Load files when the dialog opens
  const loadFiles = async (startAfter?: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const queryParams = new URLSearchParams({limit: '50'});
      if (startAfter) {
        queryParams.append('starting_after', startAfter);
      }

      // TODO: this endpoint doesn't exist
      const response = await fetch(`/api/list-files?${queryParams.toString()}`);

      if (!response.ok) {
        throw new Error('Failed to fetch files');
      }

      const data = await response.json();

      if (startAfter) {
        setFiles(prev => [...prev, ...data.items]);
      } else {
        setFiles(data.items);
      }

      // Check if there are more files to load
      setHasMore(data.has_more);

      // Update cursor for pagination
      if (data.items.length > 0) {
        setStartingAfter(data.items[data.items.length - 1].id);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'An error occurred while fetching files'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpen = (open: boolean) => {
    setIsOpen(open);
    if (open) {
      setSelectedFiles([]);
      loadFiles();
    }
  };

  const handleFileClick = (file: ScaleFile) => {
    setSelectedFiles(prevSelected => {
      // Check if the file is already selected
      const isSelected = prevSelected.some(f => f.id === file.id);

      if (isSelected) {
        // If already selected, remove it
        return prevSelected.filter(f => f.id !== file.id);
      } else {
        // Otherwise add it to selection
        return [...prevSelected, file];
      }
    });
  };

  const handleLoadMore = () => {
    if (startingAfter) {
      loadFiles(startingAfter);
    }
  };

  const handleConfirmSelection = () => {
    // Convert selected Scale files to FileAttachment format
    const newAttachments: FileAttachment[] = selectedFiles.map(file => ({
      id: `existing-${file.id}`,
      name: file.filename,
      status: 'success',
      file_id: file.id,
      size: file.size,
      type: file.mime_type || 'application/octet-stream',
      progress: 100,
    }));

    // Add to current attachments
    onFileSelect([...currentAttachments, ...newAttachments]);

    // Close the dialog
    setIsOpen(false);
  };

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function formatDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          disabled={disabled}
          className="h-8 w-8 rounded-full bg-transparent hover:bg-gray-100 dark:hover:bg-gray-800"
          aria-label="Browse existing files"
        >
          <Folder className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[625px]">
        <DialogHeader>
          <DialogTitle>Select Existing Files</DialogTitle>
        </DialogHeader>

        <div className="mt-4">
          {error && (
            <div className="mb-4 rounded-md bg-red-50 p-3 text-red-700">{error}</div>
          )}

          <ScrollArea className="h-[400px] rounded-md border">
            {files.length === 0 && !isLoading ? (
              <div className="flex h-full flex-col items-center justify-center p-4 text-center text-muted-foreground">
                <p>No files found</p>
              </div>
            ) : (
              <div className="space-y-2 p-4">
                {files.map(file => (
                  <div
                    key={file.id}
                    onClick={() => handleFileClick(file)}
                    className={`flex cursor-pointer items-center justify-between rounded-md border p-3 ${
                      selectedFiles.some(f => f.id === file.id)
                        ? 'border-primary bg-primary/10'
                        : 'hover:bg-muted'
                    } `}
                  >
                    <div className="flex items-center space-x-3">
                      <FileIcon className="h-5 w-5 text-muted-foreground" />
                      <div>
                        <p className="text-sm font-medium">{file.filename}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatFileSize(file.size)} • {formatDate(file.created_at)}
                        </p>
                      </div>
                    </div>
                    {selectedFiles.some(f => f.id === file.id) && (
                      <Check className="h-4 w-4 text-primary" />
                    )}
                  </div>
                ))}

                {hasMore && (
                  <div className="flex justify-center pt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleLoadMore}
                      disabled={isLoading}
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Loading...
                        </>
                      ) : (
                        'Load More'
                      )}
                    </Button>
                  </div>
                )}
              </div>
            )}

            {isLoading && files.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center p-4">
                <Loader2 className="mb-2 h-8 w-8 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground">Loading files...</p>
              </div>
            )}
          </ScrollArea>

          <div className="mt-4 flex justify-end space-x-2">
            <Button variant="outline" onClick={() => setIsOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleConfirmSelection}
              disabled={selectedFiles.length === 0}
            >
              Add {selectedFiles.length} {selectedFiles.length === 1 ? 'file' : 'files'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
