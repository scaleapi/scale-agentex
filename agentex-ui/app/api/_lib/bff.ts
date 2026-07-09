import { authEnabled, getSessionToken } from '@/auth';

/** Server-only platform API base for the BFF routes. Prefers SGP_API_URL, else the app URL. */
export const SGP_BASE_URL =
  process.env.SGP_API_URL ??
  (process.env.NEXT_PUBLIC_SGP_APP_URL
    ? `${process.env.NEXT_PUBLIC_SGP_APP_URL}/api`
    : undefined);

/** Return the Cookie header with the named cookie removed (null if nothing remains). */
function stripCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  const kept = header
    .split(';')
    .map(c => c.trim())
    .filter(c => {
      const eq = c.indexOf('=');
      return (eq === -1 ? c : c.slice(0, eq)) !== name;
    });
  return kept.length ? kept.join('; ') : null;
}

/**
 * Attach credentials to an upstream request's `headers` in place, so none reach client JS:
 * forward `x-selected-account-id`, drop any client-sent `authorization`, then attach the
 * session access token as a Bearer (auth mode) or forward cookies (default mode) — minus the
 * account-scoped `_jwt`, which cookie-auth backends prioritize over the header (it would pin
 * the account to the one linked in with). Identity stays via `_identityJwt`.
 */
export async function applyBffCredentials(
  req: Request,
  headers: Headers
): Promise<void> {
  const accountId = req.headers.get('x-selected-account-id');
  if (accountId) headers.set('x-selected-account-id', accountId);
  else headers.delete('x-selected-account-id');

  headers.delete('authorization');

  if (authEnabled) {
    headers.delete('cookie');
    const token = await getSessionToken(req);
    if (token?.accessToken) {
      headers.set('authorization', `Bearer ${token.accessToken}`);
    }
    return;
  }

  // Default mode: forward cookies (minus `_jwt`) for the upstream's own cookie auth.
  const cookie = stripCookie(req.headers.get('cookie'), '_jwt');
  if (cookie) headers.set('cookie', cookie);
  else headers.delete('cookie');
}
