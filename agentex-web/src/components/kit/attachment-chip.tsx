'use client';

import {cn} from '@/lib/utils';
import {cva} from 'class-variance-authority';
import {
  FileAudioIcon,
  FileIcon,
  FileImageIcon,
  FileTextIcon,
  FileVideoIcon,
} from 'lucide-react';

function contentTypeToAttachmentKind(
  contentType: string
): 'image' | 'text' | 'audio' | 'video' | 'unknown' {
  if (contentType.startsWith('image/')) {
    return 'image';
  }
  if (contentType.startsWith('text/') || contentType === 'application/json') {
    return 'text';
  }
  if (contentType.startsWith('audio/')) {
    return 'audio';
  }
  if (contentType.startsWith('video/')) {
    return 'video';
  }
  return 'unknown';
}

const rootVariants = cva('flex items-center gap-2', {
  variants: {
    size: {
      xs: 'text-xs',
      sm: 'text-sm',
      md: 'text-base',
      lg: 'text-lg',
    },
  },
  defaultVariants: {
    size: 'sm',
  },
});

const iconVariants = cva('', {
  variants: {
    size: {
      xs: 'h-3 w-3',
      sm: 'h-4 w-4',
      md: 'h-5 w-5',
      lg: 'h-6 w-6',
    },
  },
  defaultVariants: {
    size: 'sm',
  },
});

type AttachmentChipProps = {
  name: string;
  contentType: string;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
};

function AttachmentChip({name, contentType, className, size}: AttachmentChipProps) {
  const attachmentKind = contentTypeToAttachmentKind(contentType);

  return (
    <div className={cn(rootVariants({size, className}))}>
      {attachmentKind === 'image' ? (
        <FileImageIcon className={cn(iconVariants({size}))} />
      ) : attachmentKind === 'text' ? (
        <FileTextIcon className={cn(iconVariants({size}))} />
      ) : attachmentKind === 'audio' ? (
        <FileAudioIcon className={cn(iconVariants({size}))} />
      ) : attachmentKind === 'video' ? (
        <FileVideoIcon className={cn(iconVariants({size}))} />
      ) : (
        <FileIcon className={cn(iconVariants({size}))} />
      )}
      <span className="truncate">{name}</span>
    </div>
  );
}

export {AttachmentChip};
