'use client';

import { useEffect } from 'react';

import { useSession } from 'next-auth/react';

/**
 * Forces re-authentication on a terminal refresh error (the refresh token expired or was
 * revoked). Routes through the server-side auto-signin handler, which silently re-auths
 * if the provider session is still valid, otherwise shows the login. Complements the
 * middleware, which only redirects on navigation — this covers no-navigation sessions
 * (e.g. an active chat making only API calls).
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
