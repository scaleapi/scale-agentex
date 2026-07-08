import {
  NextResponse,
  type NextFetchEvent,
  type NextMiddleware,
  type NextRequest,
} from 'next/server';

import { auth, authEnabled } from '@/auth';

// Standard BFF pattern: validate the auth.js session (the wrapper reassembles
// chunked cookies, verifies + rotates tokens — middleware is a cookie-writable
// context) and route unauthenticated users through the server-side auto-signin
// handler so the sign-in → provider redirect happens server-side (avoids the
// RSC-seed refresh loop).
const authMiddleware = auth(req => {
  if (req.auth && !req.auth.error) return; // authenticated → continue

  const signInUrl = new URL('/api/auth/auto-signin', req.nextUrl.origin);
  signInUrl.searchParams.set(
    'redirect_url',
    req.nextUrl.pathname + req.nextUrl.search
  );
  return NextResponse.redirect(signInUrl);
}) as unknown as NextMiddleware;

// Gated so non-auth consumers aren't forced to log in (off = original behavior).
export function middleware(request: NextRequest, event: NextFetchEvent) {
  if (!authEnabled) return NextResponse.next();
  return authMiddleware(request, event);
}

export const config = {
  // Node runtime so the per-deployment AGENTEX_UI_AUTH_PROVIDER_ID is read at request
  // time and the auth.js session cookie can be decrypted/rotated here.
  runtime: 'nodejs',
  // Gate every page; exclude api/ (BFF + NextAuth routes self-authenticate) and
  // Next internals/static assets.
  matcher: ['/((?!api/|_next/static|_next/image|favicon.ico).*)'],
};
