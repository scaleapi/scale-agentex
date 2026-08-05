import { auth, providerId, signIn } from '@/auth';

/**
 * Server-side auto sign-in: the middleware sends unauthenticated users here so NextAuth
 * initiates the OIDC redirect (setting PKCE/state cookies) server-side. Single provider,
 * so no picker.
 */
export async function GET(req: Request): Promise<Response> {
  if (!providerId) return new Response(null, { status: 404 });
  const raw = new URL(req.url).searchParams.get('redirect_url') ?? '/';
  // Same-origin relative path only (open-redirect guard).
  const redirectTo = raw.startsWith('/') && !raw.startsWith('//') ? raw : '/';

  // Already authenticated → skip the redundant OIDC round-trip.
  const session = await auth();
  if (session && !session.error) {
    return Response.redirect(new URL(redirectTo, new URL(req.url).origin));
  }

  await signIn(providerId, { redirectTo });
  // Unreachable when signIn redirects; a 500 here signals it didn't.
  return new Response(null, { status: 500 });
}
