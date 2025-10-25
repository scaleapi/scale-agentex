'use client';

import type { HTMLAttributes } from 'react';
import { createContext } from 'react';

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import {
  oneDark,
  oneLight,
} from 'react-syntax-highlighter/dist/esm/styles/prism';

import { CopyButton } from '@/components/agentex/copy-button';
import { cn } from '@/lib/utils';

type CodeBlockContextType = {
  code: string;
};

const CodeBlockContext = createContext<CodeBlockContextType>({
  code: '',
});

export type CodeBlockProps = HTMLAttributes<HTMLDivElement> & {
  code: string;
  language: string;
  showLineNumbers?: boolean;
  showCopyButton?: boolean;
};

export const CodeBlock = ({
  code,
  language,
  showLineNumbers = false,
  showCopyButton = true,
  className,
  ...props
}: CodeBlockProps) => (
  <CodeBlockContext.Provider value={{ code }}>
    <div
      className={cn(
        'bg-background text-foreground relative max-h-[200px] w-full overflow-y-auto rounded-md border',
        className
      )}
      {...props}
    >
      <div className="relative">
        <SyntaxHighlighter
          className="overflow-hidden dark:hidden"
          codeTagProps={{
            className: 'font-mono text-sm',
            style: { whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
          }}
          customStyle={{
            margin: 0,
            padding: '1rem',
            fontSize: '0.875rem',
            background: 'hsl(var(--background))',
            color: 'hsl(var(--foreground))',
          }}
          language={language}
          lineNumberStyle={{
            color: 'hsl(var(--muted-foreground))',
            paddingRight: '1rem',
            minWidth: '2.5rem',
          }}
          showLineNumbers={showLineNumbers}
          style={oneLight}
        >
          {code}
        </SyntaxHighlighter>
        <SyntaxHighlighter
          className="hidden overflow-hidden dark:block"
          codeTagProps={{
            className: 'font-mono text-sm',
            style: { whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
          }}
          customStyle={{
            margin: 0,
            padding: '1rem',
            fontSize: '0.875rem',
            background: 'hsl(var(--background))',
            color: 'hsl(var(--foreground))',
          }}
          language={language}
          lineNumberStyle={{
            color: 'hsl(var(--muted-foreground))',
            paddingRight: '1rem',
            minWidth: '2.5rem',
          }}
          showLineNumbers={showLineNumbers}
          style={oneDark}
        >
          {code}
        </SyntaxHighlighter>
        {showCopyButton && (
          <div className="absolute top-2 right-2 flex items-center gap-2">
            <CopyButton content={code} />
          </div>
        )}
      </div>
    </div>
  </CodeBlockContext.Provider>
);
