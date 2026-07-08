import NextAuth, { type NextAuthConfig } from 'next-auth';

/**
 * Generic OIDC auth for agentex-ui — vanilla NextAuth v5, the IdP is fully env-driven.
 *
 * Client authentication is env-selected:
 *   - OIDC_PRIVATE_KEY_JWK set → private_key_jwt (matches deployments whose client
 *     registration is private_key_jwt-only)
 *   - else OIDC_CLIENT_SECRET → client_secret_post (convenient for local dev)
 *
 * Token + end-session endpoints are resolved from the issuer's OIDC discovery document,
 * so the refresh and logout paths work for any compliant IdP — not just Ory's paths.
 *
 * Route protection + auto sign-in live in middleware.ts (which redirects to the
 * server-side /api/auth/auto-signin handler) — a standard BFF pattern. Env is read
 * lazily so `next build` works without env present.
 */

const CLIENT_ASSERTION_TYPE =
  'urn:ietf:params:oauth:client-assertion-type:jwt-bearer';

// Refresh the access token this many seconds before it actually expires, so the BFF
// proxy (which only reads the cookie, it can't refresh) never forwards a stale token.
// Paired with SessionProvider's refetchInterval, which drives the jwt callback.
const REFRESH_SKEW_S = 300;

/**
 * The provider id BOTH selects the OIDC provider AND enables auth: set
 * AGENTEX_UI_AUTH_PROVIDER_ID to turn login on (unset = original direct behavior).
 * Its value must equal the callback segment registered as the IdP redirect_uri
 * (`/api/auth/callback/<id>`) — e.g. `oneauth`.
 */
export const providerId = process.env.AGENTEX_UI_AUTH_PROVIDER_ID;
export const authEnabled = !!providerId;

// `| undefined` is explicit so assignments compile under exactOptionalPropertyTypes.
declare module 'next-auth' {
  interface Session {
    // BFF: the access token is NOT exposed on the session (stays in the JWT/cookie).
    error?: string | undefined;
  }
}
declare module '@auth/core/jwt' {
  interface JWT {
    accessToken?: string | undefined;
    refreshToken?: string | undefined;
    idToken?: string | undefined;
    expiresAt?: number | undefined;
    error?: string | undefined;
  }
}

function env() {
  return {
    issuer: process.env.OIDC_ISSUER_URL ?? '',
    clientId: process.env.OIDC_CLIENT_ID ?? '',
    clientSecret: process.env.OIDC_CLIENT_SECRET,
    privateKeyJwk: process.env.OIDC_PRIVATE_KEY_JWK,
  };
}

const trimSlash = (u: string) => u.replace(/\/$/, '');

// ─── OIDC discovery ───
// The refresh + logout paths need the token/end-session endpoints. Resolve them from
// the issuer's well-known document so any IdP works (not just Ory's fixed paths);
// cache per-process and fall back to the Ory conventions if discovery is unavailable.
let discoveryPromise: Promise<Record<string, unknown>> | null = null;

function discoverOidc(): Promise<Record<string, unknown>> {
  if (!discoveryPromise) {
    const url = `${trimSlash(env().issuer)}/.well-known/openid-configuration`;
    discoveryPromise = fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`discovery ${r.status}`);
        return r.json() as Promise<Record<string, unknown>>;
      })
      .catch(() => {
        discoveryPromise = null; // don't cache a failure — retry on the next call
        return {};
      });
  }
  return discoveryPromise;
}

async function oidcTokenEndpoint(): Promise<string> {
  const endpoint = (await discoverOidc()).token_endpoint;
  // token_endpoint is mandatory in OIDC discovery; if it's missing the issuer is
  // unreachable/misconfigured — fail the refresh so the caller re-authenticates.
  if (typeof endpoint !== 'string' || !endpoint) {
    throw new Error('OIDC discovery returned no token_endpoint');
  }
  return endpoint;
}

/** end_session_endpoint for RP-initiated logout; undefined if the IdP advertises none
 *  (in which case logout is local-only — no OP round-trip to a guessed path). */
export async function oidcEndSessionEndpoint(): Promise<string | undefined> {
  const endpoint = (await discoverOidc()).end_session_endpoint;
  return typeof endpoint === 'string' && endpoint ? endpoint : undefined;
}

// ─── private_key_jwt helpers (WebCrypto only — OSS-clean, no deps) ───
function base64url(bytes: Uint8Array): string {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function importEs256Key(jwk: JsonWebKey): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['sign']
  );
}

/** Sign an RFC 7523 client_assertion for the private_key_jwt refresh call. */
async function signClientAssertion(
  clientId: string,
  tokenEndpoint: string,
  jwkJson: string
): Promise<string> {
  const jwk = JSON.parse(jwkJson) as JsonWebKey & { kid?: string };
  const key = await importEs256Key(jwk);
  const now = Math.floor(Date.now() / 1000);
  const header = {
    alg: 'ES256',
    typ: 'JWT',
    ...(jwk.kid ? { kid: jwk.kid } : {}),
  };
  const payload = {
    iss: clientId,
    sub: clientId,
    aud: tokenEndpoint,
    jti: crypto.randomUUID(),
    iat: now,
    exp: now + 60,
  };
  const enc = (o: unknown) =>
    base64url(new TextEncoder().encode(JSON.stringify(o)));
  const input = `${enc(header)}.${enc(payload)}`;
  const sig = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    key,
    new TextEncoder().encode(input)
  );
  return `${input}.${base64url(new Uint8Array(sig))}`;
}

function buildProvider(id: string) {
  const { issuer, clientId, clientSecret, privateKeyJwk } = env();
  const base = {
    id,
    name: process.env.AGENTEX_UI_AUTH_PROVIDER_NAME ?? id,
    type: 'oidc' as const,
    issuer,
    clientId,
    authorization: { params: { scope: 'openid profile email offline_access' } },
    checks: ['pkce', 'state'] as ('pkce' | 'state')[],
  };
  if (privateKeyJwk && privateKeyJwk.trim().length > 0) {
    return {
      ...base,
      client: { token_endpoint_auth_method: 'private_key_jwt' },
      // Promise<CryptoKey> — resolved before @auth/core reads it (see export).
      token: {
        clientPrivateKey: importEs256Key(
          JSON.parse(privateKeyJwk)
        ) as unknown as CryptoKey,
      },
    };
  }
  return {
    ...base,
    clientSecret: clientSecret ?? '',
    client: { token_endpoint_auth_method: 'client_secret_post' },
  };
}

function buildConfig(): NextAuthConfig {
  const { clientId, clientSecret, privateKeyJwk } = env();
  const usePkJwt = !!privateKeyJwk && privateKeyJwk.trim().length > 0;

  return {
    // AUTH_SECRET is auto-read from env by NextAuth v5 (and validated below).
    trustHost: true,
    session: { strategy: 'jwt' },
    providers: providerId ? [buildProvider(providerId)] : [],
    callbacks: {
      async jwt({ token, account }) {
        if (account) {
          token.accessToken = account.access_token;
          token.refreshToken = account.refresh_token;
          token.idToken = account.id_token;
          token.expiresAt = account.expires_at;
        }
        const expiresAt = token.expiresAt;
        if (
          expiresAt &&
          Date.now() / 1000 > expiresAt - REFRESH_SKEW_S &&
          token.refreshToken
        ) {
          try {
            const tokenEndpoint = await oidcTokenEndpoint();
            const body = new URLSearchParams({
              grant_type: 'refresh_token',
              refresh_token: token.refreshToken,
              client_id: clientId,
            });
            if (usePkJwt) {
              body.set('client_assertion_type', CLIENT_ASSERTION_TYPE);
              body.set(
                'client_assertion',
                await signClientAssertion(
                  clientId,
                  tokenEndpoint,
                  privateKeyJwk!
                )
              );
            } else {
              body.set('client_secret', clientSecret ?? '');
            }
            const res = await fetch(tokenEndpoint, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body,
            });
            if (!res.ok) {
              token.accessToken = undefined;
              token.refreshToken = undefined;
              return { ...token, error: 'RefreshAccessTokenError' };
            }
            const r = (await res.json()) as {
              access_token?: string;
              expires_at?: number;
              expires_in?: number;
              refresh_token?: string;
              id_token?: string;
            };
            token.accessToken = r.access_token;
            token.expiresAt =
              r.expires_at ??
              Math.floor(Date.now() / 1000 + (r.expires_in ?? 3600));
            if (r.refresh_token) token.refreshToken = r.refresh_token;
            if (r.id_token) token.idToken = r.id_token;
          } catch {
            token.accessToken = undefined;
            token.refreshToken = undefined;
            return { ...token, error: 'RefreshAccessTokenError' };
          }
        }
        return token;
      },
      session({ session, token }) {
        // BFF: keep the access token server-side (JWT/cookie); never on session.
        // The /api/agentex proxy reads it via getToken() and attaches the Bearer.
        if (token.error) session.error = token.error;
        return session;
      },
    },
  };
}

const config = buildConfig();

// Fail loudly on misconfiguration. Runs at module load (server start); `next build`
// env won't have AGENTEX_UI_AUTH_PROVIDER_ID set, so builds don't need runtime secrets.
if (authEnabled) {
  const { issuer, clientId, clientSecret, privateKeyJwk } = env();
  const missing: string[] = [];
  if (!issuer) missing.push('OIDC_ISSUER_URL');
  if (!clientId) missing.push('OIDC_CLIENT_ID');
  if (!clientSecret && !privateKeyJwk) {
    missing.push('OIDC_CLIENT_SECRET or OIDC_PRIVATE_KEY_JWK');
  }
  if (!process.env.AUTH_SECRET) missing.push('AUTH_SECRET');
  if (missing.length) {
    throw new Error(
      `agentex-ui: AGENTEX_UI_AUTH_PROVIDER_ID is set but required auth env is missing: ${missing.join(', ')}`
    );
  }
}

// Resolve any private_key_jwt CryptoKey (imported async) INTO the config before
// constructing NextAuth. Config MUST be a static object — a config *function*
// makes NextAuth's `auth` async, so `auth((req) => …)` returns a Promise instead
// of a callable middleware ("authMiddleware is not a function"). Top-level await
// is fine on the Node runtime the middleware uses; a no-op for client_secret.
for (const p of config.providers ?? []) {
  const tok = (p as { token?: { clientPrivateKey?: unknown } }).token;
  if (tok && tok.clientPrivateKey instanceof Promise) {
    tok.clientPrivateKey = await tok.clientPrivateKey;
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth(config);
