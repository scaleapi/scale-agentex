import { ButtonHTMLAttributes, forwardRef } from 'react';

import { Paperclip } from 'lucide-react';

import { cn } from '@/lib/utils';

interface UploadAttachmentButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  className?: string;
}

export const UploadAttachmentButton = forwardRef<
  HTMLButtonElement,
  UploadAttachmentButtonProps
>(({ className, onClick, ...props }, ref) => {
  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    // TODO: Implement attach functionality
    onClick?.(e);
  };

  return (
    <button
      ref={ref}
      type="button"
      onClick={handleClick}
      className={cn(
        'focus:ring-ring focus:ring-opacity-50 text-muted-foreground hover:text-foreground z-10 rounded-lg p-1 transition-opacity hover:opacity-80 focus:ring-2 focus:outline-none',
        className
      )}
      {...props}
    >
      <Paperclip className="h-5 w-5" />
    </button>
  );
});

UploadAttachmentButton.displayName = 'UploadAttachmentButton';
