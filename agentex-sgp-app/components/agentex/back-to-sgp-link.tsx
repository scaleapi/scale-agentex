import { Button } from '@/components/ui/button';
import { useBackToSgpHref } from '@/hooks/use-back-to-sgp-href';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { cn } from '@/lib/utils';
import { cva } from 'class-variance-authority';
import Link from 'next/link';
import { Suspense } from 'react';

const commonVariants = cva('m-0 p-0 border-0 rounded-none h-fit', {
  variants: {
    invisible: {
      true: 'invisible',
      false: '',
    },
  },
});

type Props = {
  className?: string;
};

function BackToSGPLinkImpl({ className }: Props) {
  const { sgpAccountID } = useSafeSearchParams();
  const backToSgpHref = useBackToSgpHref({
    sgpAccountID,
  });

  return (
    <Button
      className={commonVariants({
        invisible: backToSgpHref === null,
        className,
      })}
      asChild
      variant="link"
    >
      <Link
        className={commonVariants({ invisible: backToSgpHref === null })}
        aria-hidden={backToSgpHref === null}
        href={backToSgpHref ?? '#'}
      >
        Back to SGP
      </Link>
    </Button>
  );
}

export function BackToSGPLink({ ...props }: Props) {
  return (
    <Suspense
      fallback={
        <Link
          className={cn(
            commonVariants({ invisible: true, className: props.className })
          )}
          aria-hidden
          href="#"
        >
          Back to SGP
        </Link>
      }
    >
      <BackToSGPLinkImpl {...props} />
    </Suspense>
  );
}
