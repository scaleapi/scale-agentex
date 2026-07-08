'use client';

import { useEffect } from 'react';

import { useSession } from 'next-auth/react';

/**
 * Forces re-auth on a terminal refresh error (refresh token expired/revoked) via the
 * server-side auto-signin handler. Complements the middleware (which only redirects on
 * navigation) — this covers sessions making only API calls, e.g. an active chat.
 */
export function SessionGuard() {
  const { data: session } = useSession();
  const error = session?.error;

  useEffect(() => {
    if (error !== 'RefreshAccessTokenError') return;
    const redirect = window.location.pathname + window.location.search;
    window.location.href = `/api/auth/auto-signin?redirect_url=${encodeURIComponent(redirect)}`;
  }, [error]);

  return null;
}
