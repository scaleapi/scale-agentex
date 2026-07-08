import { getToken } from 'next-auth/jwt';

import { oidcEndSessionEndpoint, signOut } from '@/auth';

/**
 * RP-initiated (SSO) logout: clear the local NextAuth session AND end the provider's
 * SSO (OP) session, so middleware auto-signin doesn't silently log the user back in.
 * The id_token is read server-side (getToken) and never exposed on the session.
 *
 * POST-only, by design: logout is destructive (it can end the whole IdP SSO session), and
 * a SameSite=Lax session cookie is NOT sent on cross-site POSTs — so a crafted cross-site
 * link can't trigger it (GET-logout CSRF). The client POSTs here and then navigates to the
 * returned RP-initiated logout `url`.
 */
export async function POST(req: Request): Promise<Response> {
  const token = await getToken({
    req: req as never,
    secret: process.env.AUTH_SECRET ?? '',
  });
  const idToken = token?.idToken as string | undefined;

  await signOut({ redirect: false }); // clears the session cookie

  const origin = process.env.AUTH_URL ?? new URL(req.url).origin;
  const endSession = await oidcEndSessionEndpoint();
  if (endSession && idToken) {
    const url = new URL(endSession);
    url.searchParams.set('id_token_hint', idToken);
    url.searchParams.set('post_logout_redirect_uri', origin);
    return Response.json({ url: url.toString() });
  }
  return Response.json({ url: origin });
}
