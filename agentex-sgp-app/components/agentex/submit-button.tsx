import { Send } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ButtonHTMLAttributes, forwardRef } from 'react';

interface SubmitButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  className?: string;
  disabled?: boolean;
}

export const SubmitButton = forwardRef<HTMLButtonElement, SubmitButtonProps>(
  ({ className, disabled = false, ...props }, ref) => {
    return (
      <button
        ref={ref}
        type="submit"
        disabled={disabled}
        className={cn(
          'z-10 hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-ring focus:ring-opacity-50 rounded-full',
          'flex items-center justify-center w-8 h-8 bg-current/10 border border-current/20',
          disabled && 'cursor-not-allowed opacity-50',
          className
        )}
        {...props}
      >
        <Send className="h-4 w-4" />
      </button>
    );
  }
);

SubmitButton.displayName = 'SubmitButton';
