'use client';

import { useCallback, useState, type KeyboardEvent } from 'react';

import { X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type TagInputProps = {
  value: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
};

export function TagInput({
  value,
  onChange,
  disabled = false,
  placeholder = 'Type and press Enter',
  className,
}: TagInputProps) {
  const [inputValue, setInputValue] = useState('');

  const addTag = useCallback(
    (tag: string) => {
      const trimmed = tag.trim();
      if (trimmed && !value.includes(trimmed)) {
        onChange([...value, trimmed]);
      }
      setInputValue('');
    },
    [value, onChange]
  );

  const removeTag = useCallback(
    (tagToRemove: string) => {
      onChange(value.filter(tag => tag !== tagToRemove));
    },
    [value, onChange]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addTag(inputValue);
      } else if (e.key === 'Backspace' && !inputValue && value.length > 0) {
        removeTag(value[value.length - 1]!);
      }
    },
    [inputValue, value, addTag, removeTag]
  );

  return (
    <div
      className={cn(
        'border-input flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border px-3 py-1.5 shadow-xs',
        disabled && 'cursor-not-allowed opacity-50',
        className
      )}
    >
      {value.map(tag => (
        <Badge key={tag} variant="secondary" className="gap-1 pr-1">
          {tag}
          {!disabled && (
            <button
              type="button"
              onClick={() => removeTag(tag)}
              className="hover:text-destructive rounded-sm"
            >
              <X className="size-3" />
            </button>
          )}
        </Badge>
      ))}
      <input
        type="text"
        value={inputValue}
        onChange={e => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={value.length === 0 ? placeholder : ''}
        className="placeholder:text-muted-foreground min-w-[120px] flex-1 bg-transparent text-sm outline-none disabled:cursor-not-allowed"
      />
    </div>
  );
}
