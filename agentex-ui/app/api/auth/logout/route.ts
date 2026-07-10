import { getSessionToken, oidcEndSessionEndpoint, signOut } from '@/auth';

/**
 * RP-initiated (SSO) logout: clear the local session AND end the provider's SSO session,
 * so middleware auto-signin doesn't silently log the user back in. The id_token is read
 * server-side and never exposed on the session.
 *
 * POST-only: a SameSite=Lax cookie isn't sent on cross-site POSTs, so a crafted link can't
 * trigger logout (GET-logout CSRF). The client POSTs, then navigates to the returned `url`.
 */
export async function POST(req: Request): Promise<Response> {
  const token = await getSessionToken(req);
  const idToken = token?.idToken;

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
