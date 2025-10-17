import * as React from 'react';

import { cn } from '@/lib/utils';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        'border-input placeholder:text-muted-foreground text-foreground flex field-sizing-content min-h-16 w-full max-w-full min-w-0 box-border rounded-md border px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[1px] focus-visible:ring-[#756BA2] disabled:cursor-not-allowed disabled:opacity-50 md:text-sm overflow-auto break-words',
        className
      )}
      {...props}
    />
  );
}

export { Textarea };
