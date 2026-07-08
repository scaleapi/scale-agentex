import { applyBffCredentials } from '@/app/api/_lib/bff';

/**
 * BFF proxy for the Agentex API. The browser ALWAYS calls this same-origin route, so
 * the backend origin + credentials never touch client JS. Credentials (access token
 * or forwarded cookies, plus x-selected-account-id) are applied server-side by
 * applyBffCredentials — see app/api/_lib/bff.ts.
 */
export const dynamic = 'force-dynamic';

// Server-only upstream — the client only ever calls /api/agentex, so the backend URL
// stays out of the browser bundle.
const UPSTREAM = (
  process.env.AGENTEX_API_URL ?? 'http://localhost:5003'
).replace(/\/$/, '');

// Hop-by-hop / spoofable request headers to drop before forwarding. `cookie` and
// `authorization` are managed by applyBffCredentials, not stripped here.
const STRIP_REQ = ['host', 'connection', 'content-length'];
const STRIP_RES = [
  'content-encoding',
  'content-length',
  'transfer-encoding',
  'connection',
];

async function proxy(
  req: Request,
  ctx: { params: Promise<{ path?: string[] }> }
): Promise<Response> {
  const { path = [] } = await ctx.params;
  const search = new URL(req.url).search;
  const target = `${UPSTREAM}/${path.join('/')}${search}`;

  const headers = new Headers(req.headers);
  for (const h of STRIP_REQ) headers.delete(h);
  await applyBffCredentials(req, headers);

  const method = req.method.toUpperCase();
  const hasBody = method !== 'GET' && method !== 'HEAD';
  const upstream = await fetch(target, {
    method,
    headers,
    body: hasBody ? req.body : undefined,
    redirect: 'manual',
    // @ts-expect-error `duplex` is required to stream a request body (undici)
    duplex: 'half',
  });

  // Pass the upstream body through unbuffered so SSE / streaming responses work.
  const resHeaders = new Headers(upstream.headers);
  for (const h of STRIP_RES) resHeaders.delete(h);
  return new Response(upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  });
}

export {
  proxy as DELETE,
  proxy as GET,
  proxy as HEAD,
  proxy as OPTIONS,
  proxy as PATCH,
  proxy as POST,
  proxy as PUT,
};
