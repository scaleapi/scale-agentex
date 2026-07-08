import { providerId, signIn } from '@/auth';

/**
 * Server-side auto sign-in: the middleware sends unauthenticated users here so NextAuth
 * initiates the OIDC redirect (setting PKCE/state cookies) server-side. Single provider,
 * so no picker.
 */
export async function GET(req: Request): Promise<Response> {
  if (!providerId) return new Response(null, { status: 404 });
  const redirectTo = new URL(req.url).searchParams.get('redirect_url') ?? '/';
  await signIn(providerId, { redirectTo });
  // Unreachable when signIn redirects; a 500 here signals it didn't.
  return new Response(null, { status: 500 });
}
