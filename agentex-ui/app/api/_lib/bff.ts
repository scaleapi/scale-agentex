/**
 * Server-only platform API upstream, shared by the platform-backed BFF routes
 * (/api/feedback, /api/user-info). SGP_API_URL preferred; falls back to the dashboard
 * app origin's /api.
 */
export const SGP_BASE_URL =
  process.env.SGP_API_URL ??
  (process.env.NEXT_PUBLIC_SGP_APP_URL
    ? `${process.env.NEXT_PUBLIC_SGP_APP_URL}/api`
    : undefined);

/**
 * Apply BFF credentials to an outgoing upstream request's `headers`, in place, so no
 * credential reaches client JS. Shared by every /api/* proxy (agentex, platform):
 *   - `x-selected-account-id` from the client (sourced from the account_id query param);
 *     forwarded as-is — the upstream authorizes the principal's access to the account.
 *   - any client-supplied `authorization` is dropped so a client can't inject its own
 *     bearer token; the request cookies are forwarded for the upstream's cookie auth.
 */
export async function applyBffCredentials(
  req: Request,
  headers: Headers
): Promise<void> {
  const accountId = req.headers.get('x-selected-account-id');
  if (accountId) headers.set('x-selected-account-id', accountId);
  else headers.delete('x-selected-account-id');

  // Credentials are server-managed: never trust a client-sent Authorization header.
  headers.delete('authorization');

  const cookie = req.headers.get('cookie');
  if (cookie) headers.set('cookie', cookie);
  else headers.delete('cookie');
}
