import { Paperclip } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ButtonHTMLAttributes, forwardRef } from 'react';

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
    console.log('TODO: Implement attach functionality');
    onClick?.(e);
  };

  return (
    <button
      ref={ref}
      type="button"
      onClick={handleClick}
      className={cn(
        'z-10 hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-ring focus:ring-opacity-50 rounded-lg p-1 text-muted-foreground hover:text-foreground',
        className
      )}
      {...props}
    >
      <Paperclip className="h-5 w-5" />
    </button>
  );
});

UploadAttachmentButton.displayName = 'UploadAttachmentButton';
