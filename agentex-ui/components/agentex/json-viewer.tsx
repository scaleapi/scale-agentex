'use client';

import { useState } from 'react';

import { cva } from 'class-variance-authority';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { CopyButton } from '@/components/agentex/copy-button';
import { cn } from '@/lib/utils';

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

const valueStyles = cva('', {
  variants: {
    type: {
      string: 'text-green-600 dark:text-green-400',
      number: 'text-blue-600 dark:text-blue-400',
      boolean: 'text-purple-600 dark:text-purple-400',
      null: 'text-orange-500',
      object: 'text-muted-foreground',
      array: 'text-muted-foreground',
    },
  },
});

function serializeValue(data: JsonValue): string {
  if (typeof data === 'object' && data !== null) {
    return JSON.stringify(data, null, 2);
  }
  if (typeof data === 'string') {
    return data;
  }
  return String(data);
}

interface JsonCollapsibleProps extends React.HTMLAttributes<HTMLDivElement> {
  copyContent: string;
  collapsedContent: React.ReactNode;
  expandedContent: React.ReactNode;
  shouldBeExpanded?: boolean;
  keyName?: string | undefined;
}

function JsonCollapsible({
  copyContent,
  collapsedContent,
  expandedContent,
  shouldBeExpanded = false,
  keyName,
  ...props
}: JsonCollapsibleProps) {
  const [isExpanded, setIsExpanded] = useState(shouldBeExpanded);

  return (
    <div {...props}>
      <div className="hover:bg-accent/50 group/line flex items-center gap-2 rounded px-2">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex flex-1 items-center gap-1 font-mono text-sm"
        >
          <div className="flex h-4 w-4 items-center justify-center">
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </div>
          {keyName && (
            <span className="text-muted-foreground">{keyName}: </span>
          )}
          <span className="text-muted-foreground">{collapsedContent}</span>
        </button>
        <div className="opacity-0 transition-opacity group-hover/line:opacity-100">
          <CopyButton content={copyContent} />
        </div>
      </div>
      {isExpanded && <div>{expandedContent}</div>}
    </div>
  );
}

interface JsonNodeProps {
  data: JsonValue;
  keyName?: string;
  level?: number;
  currentDepth?: number;
  maxOpenDepth?: number;
}

function JsonNode({
  data,
  keyName,
  level = 0,
  currentDepth = 0,
  maxOpenDepth = 0,
}: JsonNodeProps) {
  // Try to parse JSON strings
  let parsedData = data;
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data);
      if (typeof parsed === 'object' && parsed !== null) {
        parsedData = parsed;
      }
    } catch {
      // Not valid JSON, keep as string
    }
  }

  const copyContent = keyName
    ? `${keyName}: ${serializeValue(parsedData)}`
    : serializeValue(parsedData);

  const indentClassName = level > 0 ? 'ml-4' : '';
  const [isExpanded, setIsExpanded] = useState(false);

  // Calculate if this node should be expanded based on depth
  // maxOpenDepth < 0 means expand all (treat as infinity)
  const shouldExpand = maxOpenDepth < 0 || currentDepth < maxOpenDepth;

  let content = null;
  let dataType:
    | 'string'
    | 'number'
    | 'boolean'
    | 'null'
    | 'object'
    | 'array'
    | null = null;

  // Render arrays
  if (Array.isArray(parsedData) && parsedData.length > 0) {
    return (
      <JsonCollapsible
        keyName={keyName}
        copyContent={copyContent}
        collapsedContent={`[${parsedData.length} ${parsedData.length === 1 ? 'item' : 'items'}]`}
        expandedContent={parsedData.map((item, index) => (
          <JsonNode
            key={index}
            data={item}
            level={level + 1}
            currentDepth={currentDepth + 1}
            maxOpenDepth={maxOpenDepth}
          />
        ))}
        shouldBeExpanded={shouldExpand}
        className={indentClassName}
      />
    );
  }

  // Render objects
  if (
    typeof parsedData === 'object' &&
    parsedData !== null &&
    Object.keys(parsedData).length > 0
  ) {
    const entries = Object.entries(parsedData);

    return (
      <JsonCollapsible
        keyName={keyName}
        copyContent={copyContent}
        collapsedContent={
          <>
            {'{'}
            {entries.length} {entries.length === 1 ? 'key' : 'keys'}
            {'}'}
          </>
        }
        expandedContent={entries.map(([key, value]) => (
          <JsonNode
            key={key}
            data={value}
            keyName={key}
            level={level + 1}
            currentDepth={currentDepth + 1}
            maxOpenDepth={maxOpenDepth}
          />
        ))}
        shouldBeExpanded={shouldExpand}
        className={indentClassName}
      />
    );
  }

  // Check if string is long (more than 6 lines worth of characters, ~80 chars per line)
  const isLongString =
    typeof parsedData === 'string' && parsedData.length > 480;

  switch (typeof parsedData) {
    case 'string':
      dataType = 'string';
      content = `"${parsedData}"`;
      break;
    case 'number':
      dataType = 'number';
      content = parsedData.toString();
      break;
    case 'boolean':
      dataType = 'boolean';
      content = parsedData.toString();
      break;
    case 'object':
      if (parsedData === null) {
        dataType = 'null';
        content = 'null';
      } else if (Array.isArray(parsedData)) {
        content = '[]';
        dataType = 'array';
      } else {
        content = '{}';
        dataType = 'object';
      }
      break;
    default:
      dataType = 'null';
      content = 'null';
  }

  return (
    <div
      className={cn(
        'hover:bg-accent/50 group/line flex items-center gap-2 rounded px-2',
        indentClassName
      )}
    >
      <div
        className={cn(
          'flex-1 font-mono text-sm',
          isLongString && 'cursor-pointer'
        )}
        onClick={e => {
          if (isLongString) {
            // Only toggle if not clicking the copy button
            const target = e.target as HTMLElement;
            if (!target.closest('button')) {
              setIsExpanded(!isExpanded);
            }
          }
        }}
      >
        {keyName && <span className="text-muted-foreground">{keyName}: </span>}
        <span
          className={cn(
            valueStyles({ type: dataType }),
            isLongString && !isExpanded && 'line-clamp-6'
          )}
        >
          {content}
        </span>
      </div>
      <CopyButton
        content={copyContent}
        className="opacity-0 transition-opacity group-hover/line:opacity-100"
      />
    </div>
  );
}

interface JsonViewerProps {
  data: JsonValue;
  defaultOpenDepth?: number;
  className?: string;
}

export function JsonViewer({
  data,
  defaultOpenDepth = 0,
  className,
}: JsonViewerProps) {
  return (
    <div
      className={cn(
        'bg-muted/30 overflow-auto rounded-md border p-3',
        className
      )}
    >
      <JsonNode data={data} currentDepth={0} maxOpenDepth={defaultOpenDepth} />
    </div>
  );
}
