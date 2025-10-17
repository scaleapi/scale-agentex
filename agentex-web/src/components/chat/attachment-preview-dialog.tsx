'use client';

import {AttachmentChip} from '@/components/kit/attachment-chip';
import {Button} from '@/components/ui/button';
import {Dialog, DialogContent, DialogFooter, DialogHeader} from '@/components/ui/dialog';
import {cn} from '@/lib/utils';
import {Download} from 'lucide-react';

type AttachmentPreviewDialogProps = {
  name: string;
  contentType: string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenInBrowser?: () => void;
  onDownload?: () => void;
  className?: string;
};

function AttachmentPreviewDialog({
  name,
  contentType,
  isOpen,
  onOpenChange,
  onOpenInBrowser,
  onDownload,
  className,
}: AttachmentPreviewDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className={cn('max-w-md', className)}>
        <DialogHeader>
          <AttachmentChip name={name} contentType={contentType} size="sm" />
        </DialogHeader>

        <DialogFooter className="flex justify-center gap-4">
          {onOpenInBrowser !== undefined && (
            <Button
              onClick={onOpenInBrowser}
              onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onOpenInBrowser();
                }
              }}
              className="flex items-center gap-2"
            >
              Open in Browser
            </Button>
          )}
          {onDownload !== undefined && (
            <Button
              onClick={onDownload}
              onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onDownload();
                }
              }}
              variant="outline"
              className="flex items-center gap-2"
            >
              <Download className="h-4 w-4" />
              Download
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export {AttachmentPreviewDialog};
