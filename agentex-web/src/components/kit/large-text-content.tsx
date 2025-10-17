'use client';

import {Alert, AlertDescription} from '@/components/ui/alert';
import {Skeleton} from '@/components/ui/skeleton';
import {parseTextContent} from '@/lib/parse-text-content';
import {AlertCircle} from 'lucide-react';
import {lazy, Suspense, use, useMemo} from 'react';

const ReactJsonView = lazy(() => import('@microlink/react-json-view'));

type LargeTextContentImplProps = {
  displayBodyPromise: Promise<
    | {
        value: string | number | bigint | boolean | null | undefined | object;
        error?: undefined;
      }
    | {value?: undefined; error: string}
  >;
};

function LargeTextContentImpl({displayBodyPromise}: LargeTextContentImplProps) {
  const {value, error} = use(displayBodyPromise);

  const showJsonView = typeof value === 'object' && value !== null;
  const isNoContent =
    value === undefined || (typeof value === 'string' && value.length === 0);

  // parse error
  if (error !== undefined) {
    return (
      <Alert className="border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-900/20">
        <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
        <AlertDescription className="text-yellow-800 dark:text-yellow-200">
          Content is too large or complex to display: {error}
        </AlertDescription>
      </Alert>
    );
  }

  return showJsonView ? (
    <div className="overflow-x-auto text-sm" onClick={e => e.stopPropagation()}>
      <ReactJsonView
        src={value}
        name={false}
        collapsed={2}
        enableClipboard={false}
        displayDataTypes={false}
        style={{fontSize: '13px'}}
        collapseStringsAfterLength={100}
      />
    </div>
  ) : (
    <pre
      className="whitespace-pre-wrap text-wrap text-sm"
      onClick={e => e.stopPropagation()}
    >
      {isNoContent ? 'No content' : value === null ? 'null' : value}
    </pre>
  );
}

type LargeTextContentProps = {
  content: unknown;
};

function LargeTextContent({content}: LargeTextContentProps) {
  const displayBodyPromise = useMemo(
    () =>
      parseTextContent(content)
        .then(value => ({value}))
        .catch((error: unknown) => ({
          error:
            typeof error === 'object' &&
            error !== null &&
            'message' in error &&
            typeof error.message === 'string'
              ? error.message
              : 'Error parsing content',
        })),
    [content]
  );

  return (
    <Suspense fallback={<Skeleton className="h-24 w-full" />}>
      <LargeTextContentImpl displayBodyPromise={displayBodyPromise} />
    </Suspense>
  );
}

export {LargeTextContent};
