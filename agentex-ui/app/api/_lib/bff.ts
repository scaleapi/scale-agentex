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
 * forward `x-selected-account-id` (the upstream authorizes the account), drop any
 * client-sent `authorization`, and forward cookies for the upstream's own auth — minus the
 * account-scoped `_jwt` (access-profile) cookie. Cookie-auth backends prioritize `_jwt` over
 * `x-selected-account-id`, so leaving it would pin the account to the one the user linked in
 * with and ignore the selected account; identity still comes from `_identityJwt`.
 */
export async function applyBffCredentials(
  req: Request,
  headers: Headers
): Promise<void> {
  const accountId = req.headers.get('x-selected-account-id');
  if (accountId) headers.set('x-selected-account-id', accountId);
  else headers.delete('x-selected-account-id');

  headers.delete('authorization');

  const cookie = stripCookie(req.headers.get('cookie'), '_jwt');
  if (cookie) headers.set('cookie', cookie);
  else headers.delete('cookie');
}
