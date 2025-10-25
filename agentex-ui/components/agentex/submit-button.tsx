import { ButtonHTMLAttributes, forwardRef } from 'react';

import { Send } from 'lucide-react';

import { cn } from '@/lib/utils';

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
          'focus:ring-ring focus:ring-opacity-50 z-10 rounded-full transition-opacity hover:opacity-80 focus:ring-2 focus:outline-none',
          'flex h-8 w-8 items-center justify-center border border-current/20 bg-current/10',
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
