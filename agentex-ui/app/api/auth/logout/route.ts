import { NextResponse } from 'next/server';

import { getToken } from 'next-auth/jwt';

import { signOut } from '@/auth';

/**
 * RP-initiated (SSO) logout: clear the local NextAuth session AND end the provider's
 * SSO (OP) session, so middleware auto-signin doesn't silently log the user back in.
 * The id_token is read server-side (getToken) and never exposed on the session.
 */
export async function GET(req: Request): Promise<Response> {
  const token = await getToken({
    req: req as never,
    secret: process.env.AUTH_SECRET ?? '',
  });
  const idToken = token?.idToken as string | undefined;

  await signOut({ redirect: false }); // clears the session cookie

  const origin = process.env.AUTH_URL ?? new URL(req.url).origin;
  const issuer = process.env.OIDC_ISSUER_URL;
  if (issuer && idToken) {
    const url = new URL(`${issuer}/oauth2/sessions/logout`);
    url.searchParams.set('id_token_hint', idToken);
    url.searchParams.set('post_logout_redirect_uri', origin);
    return NextResponse.redirect(url);
  }
  return NextResponse.redirect(origin);
}
