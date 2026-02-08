'use client';

import { useMemo, useEffect, useState, useCallback } from 'react';

import { cva } from 'class-variance-authority';
import {
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { CopyButton } from '@/components/ui/copy-button';
import { serializeValue } from '@/lib/json-utils';
import type { JsonValue } from '@/lib/types';
import { cn } from '@/lib/utils';

const URL_REGEX =
  /https?:\/\/(www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_+.~#?&//=]*)/g;

const valueStyles = cva('', {
  variants: {
    type: {
      string: 'text-green-700 dark:text-green-300',
      number: 'text-blue-700 dark:text-blue-300',
      boolean: 'text-purple-700 dark:text-purple-300',
      null: 'text-orange-700 dark:text-orange-300',
      object: 'text-muted-foreground',
      array: 'text-muted-foreground',
    },
  },
});

function LinkifiedString({ value }: { value: string }) {
  const parts: (string | React.ReactElement)[] = [];
  let lastIndex = 0;

  const matches = value.matchAll(URL_REGEX);

  for (const match of matches) {
    if (match.index !== undefined && match.index > lastIndex) {
      parts.push(value.substring(lastIndex, match.index));
    }

    const url = match[0];
    parts.push(
      <a
        key={match.index}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="underline"
        onClick={e => e.stopPropagation()}
      >
        {url}
      </a>
    );

    lastIndex = (match.index ?? 0) + url.length;
  }

  if (lastIndex < value.length) {
    parts.push(value.substring(lastIndex));
  }

  if (parts.length === 0) {
    return <>{value}</>;
  }

  return <>{parts}</>;
}

type JsonCollapsibleProps = React.HTMLAttributes<HTMLDivElement> & {
  copyContent: string;
  collapsedContent: React.ReactNode;
  expandedContent: React.ReactNode;
  shouldBeExpanded?: boolean;
  forceExpandState?: boolean | null;
  keyName?: string | undefined;
  extraButtons?: React.ReactNode;
  showCopyButton?: boolean;
};

function JsonCollapsible({
  copyContent,
  collapsedContent,
  expandedContent,
  shouldBeExpanded = false,
  forceExpandState = null,
  keyName,
  extraButtons,
  showCopyButton = true,
  ...props
}: JsonCollapsibleProps) {
  const [isExpanded, setIsExpanded] = useState(() =>
    forceExpandState !== null ? forceExpandState : shouldBeExpanded
  );

  useEffect(() => {
    if (forceExpandState !== null) {
      setIsExpanded(forceExpandState);
    }
  }, [forceExpandState]);

  return (
    <div {...props}>
      <div className="hover:bg-accent/30 group/line flex items-center gap-2 rounded px-2">
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
        <div className="flex items-center gap-2">
          {extraButtons}
          {showCopyButton && (
            <div className="opacity-0 transition-opacity group-hover/line:opacity-100">
              <CopyButton
                content={copyContent}
                className="hover:bg-accent/50"
              />
            </div>
          )}
        </div>
      </div>
      {isExpanded && <div>{expandedContent}</div>}
    </div>
  );
}

type JsonNodeProps = {
  data: JsonValue;
  keyName?: string;
  level?: number;
  currentDepth?: number;
  maxOpenDepth?: number;
  forceExpandState?: boolean | null;
  extraButtons?: React.ReactNode;
};

function JsonNode({
  data,
  keyName,
  level = 0,
  currentDepth = 0,
  maxOpenDepth = 0,
  forceExpandState = null,
  extraButtons,
}: JsonNodeProps) {
  let parsedData = data;
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data);
      if (typeof parsed === 'object' && parsed !== null) {
        parsedData = parsed;
      }
    } catch {}
  }

  const copyContent = keyName
    ? `${keyName}: ${serializeValue(parsedData)}`
    : serializeValue(parsedData);

  const indentClassName = level > 0 ? 'ml-4' : '';
  const [isExpanded, setIsExpanded] = useState(false);
  const shouldExpand = maxOpenDepth < 0 || currentDepth < maxOpenDepth;

  let content: React.ReactNode = null;
  let dataType:
    | 'string'
    | 'number'
    | 'boolean'
    | 'null'
    | 'object'
    | 'array'
    | null = null;

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
            forceExpandState={forceExpandState}
          />
        ))}
        shouldBeExpanded={shouldExpand}
        forceExpandState={forceExpandState}
        extraButtons={extraButtons}
        showCopyButton={!extraButtons}
        className={indentClassName}
      />
    );
  }

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
            forceExpandState={forceExpandState}
          />
        ))}
        shouldBeExpanded={shouldExpand}
        forceExpandState={forceExpandState}
        extraButtons={extraButtons}
        showCopyButton={!extraButtons}
        className={indentClassName}
      />
    );
  }

  const isLongString =
    typeof parsedData === 'string' && parsedData.length > 480;

  switch (typeof parsedData) {
    case 'string':
      dataType = 'string';
      content = (
        <>
          &quot;
          <LinkifiedString value={parsedData} />
          &quot;
        </>
      );
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
        'hover:bg-accent/30 group/line flex items-center gap-2 rounded px-2',
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
        className="hover:bg-accent/50 opacity-0 transition-opacity group-hover/line:opacity-100"
      />
    </div>
  );
}

type JsonViewerProps = {
  data: JsonValue;
  defaultOpenDepth?: number;
  className?: string;
};

export function JsonViewer({
  data,
  defaultOpenDepth = 0,
  className,
}: JsonViewerProps) {
  const [forceExpandState, setForceExpandState] = useState<boolean | null>(
    null
  );

  const shouldShowExpand = useMemo(() => {
    return forceExpandState === null
      ? defaultOpenDepth === 0
      : !forceExpandState;
  }, [forceExpandState, defaultOpenDepth]);

  const toggleForceExpandState = useCallback(() => {
    setForceExpandState(shouldShowExpand);
  }, [shouldShowExpand]);

  const extraButtons = useMemo(() => {
    return (
      <>
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleForceExpandState}
          className="text-muted-foreground hover:text-foreground hover:bg-accent/30 h-6 gap-1.5 text-xs"
        >
          {shouldShowExpand ? (
            <>
              <ChevronsUpDown className="h-3 w-3" />
              Expand All
            </>
          ) : (
            <>
              <ChevronsDownUp className="h-3 w-3" />
              Collapse All
            </>
          )}
        </Button>
        <CopyButton
          content={JSON.stringify(data, null, 2)}
          className="hover:bg-accent/30"
        />
      </>
    );
  }, [data, shouldShowExpand, toggleForceExpandState]);

  return (
    <div
      className={cn(
        'bg-muted/30 overflow-auto rounded-md border p-3',
        className
      )}
    >
      <JsonNode
        data={data}
        currentDepth={0}
        maxOpenDepth={defaultOpenDepth}
        forceExpandState={forceExpandState}
        extraButtons={extraButtons}
      />
    </div>
  );
}
