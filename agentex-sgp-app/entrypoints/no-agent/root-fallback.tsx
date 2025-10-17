import { Skeleton } from '@/components/ui/skeleton';
import { memo } from 'react';
import { Header } from './header';

type Props = {
  errorMessage: string | null;
};

function RootFallbackImpl({ errorMessage }: Props) {
  return (
    <>
      <Header />
      <main className="flex-1 flex justify-center">
        {errorMessage ? (
          <div className="text-destructive font-bold text-lg m-4">
            {errorMessage}
          </div>
        ) : (
          <Skeleton className="flex-1 max-w-[min(100%-var(--spacing)*4,var(--max-page-content-width))] my-8 h-96" />
        )}
      </main>
    </>
  );
}

export const RootFallback = memo(RootFallbackImpl);
