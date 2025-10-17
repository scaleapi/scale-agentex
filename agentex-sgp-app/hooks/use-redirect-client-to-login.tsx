'use client';

import { useAppConfig } from '@/hooks/use-app-config';
import { useRouter } from 'next/navigation';
import { RefObject, useEffect, useRef } from 'react';

function redirectClientToLogin({
  sgpAppURL,
  sourceHref,
  router,
}: {
  sgpAppURL: string | undefined;
  sourceHref: string | undefined;
  router: ReturnType<typeof useRouter>;
}): void {
  try {
    if (!sgpAppURL) {
      return;
    }
    const url = new URL(sgpAppURL);
    // TODO: keep in sync with egp-annotation when this changes
    url.pathname = url.pathname.replace(/\/$/, '') + '/login';
    if (sourceHref) {
      url.searchParams.set('redirect_url', sourceHref);
    }

    router.push(url.toString());
  } catch {
    return;
  }
}

/**
 * Tries to redirect the user to the login page. Does nothing if there was an error.
 *
 * @param source where to come back to after login
 * @returns never if redirect was successful, void otherwise
 */
export function useRedirectClientToLoginRef(): RefObject<() => void> {
  const { sgpAppURL } = useAppConfig();
  const router = useRouter();

  const ref = useRef(() =>
    redirectClientToLogin({
      sgpAppURL: sgpAppURL,
      sourceHref:
        typeof window !== 'undefined' ? window.location.href : undefined,
      router,
    })
  );

  useEffect(() => {
    ref.current = () =>
      redirectClientToLogin({
        sgpAppURL: sgpAppURL,
        sourceHref:
          typeof window !== 'undefined' ? window.location.href : undefined,
        router,
      });
  }, [router]);

  return ref;
}
