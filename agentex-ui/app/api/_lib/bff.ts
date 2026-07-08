/** Server-only platform API base for the BFF routes. Prefers SGP_API_URL, else the app URL. */
export const SGP_BASE_URL =
  process.env.SGP_API_URL ??
  (process.env.NEXT_PUBLIC_SGP_APP_URL
    ? `${process.env.NEXT_PUBLIC_SGP_APP_URL}/api`
    : undefined);

/**
 * Attach credentials to an upstream request's `headers` in place, so none reach client JS:
 * forward `x-selected-account-id` (the upstream authorizes the account), drop any
 * client-sent `authorization`, and forward cookies for the upstream's own auth.
 */
export async function applyBffCredentials(
  req: Request,
  headers: Headers
): Promise<void> {
  const accountId = req.headers.get('x-selected-account-id');
  if (accountId) headers.set('x-selected-account-id', accountId);
  else headers.delete('x-selected-account-id');

  headers.delete('authorization');

  const cookie = req.headers.get('cookie');
  if (cookie) headers.set('cookie', cookie);
  else headers.delete('cookie');
}
