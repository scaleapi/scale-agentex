import { providerId, signIn } from '@/auth';

/**
 * Server-side auto sign-in: middleware sends unauthenticated users here so the
 * OIDC redirect to the provider is initiated server-side (NextAuth sets the
 * PKCE/state cookies + performs the redirect). Single provider, so no picker page.
 *
 * Relies on `signIn` performing the redirect (throwing NEXT_REDIRECT) in a GET
 * route handler; if it returns a URL instead, use
 * `return Response.redirect(await signIn(providerId, { redirectTo, redirect: false }))`.
 */
export async function GET(req: Request): Promise<Response> {
  if (!providerId) return new Response(null, { status: 404 });
  const redirectTo = new URL(req.url).searchParams.get('redirect_url') ?? '/';
  await signIn(providerId, { redirectTo });
  // Unreachable when signIn redirects; a 500 here signals it didn't.
  return new Response(null, { status: 500 });
}
