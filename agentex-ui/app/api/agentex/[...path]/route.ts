import { applyBffCredentials } from '@/app/api/_lib/bff';

/**
 * Same-origin BFF proxy for the Agentex API, so the upstream URL and credentials never
 * reach client JS. applyBffCredentials attaches credentials server-side.
 */
export const dynamic = 'force-dynamic';

const UPSTREAM = (
  process.env.AGENTEX_API_URL ?? 'http://localhost:5003'
).replace(/\/$/, '');

// Hop-by-hop headers to drop. Credential headers (cookie/authorization) are handled by
// applyBffCredentials, not here.
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
  // Don't leak an upstream (internal) redirect target to the browser.
  if (upstream.status >= 300 && upstream.status < 400) {
    resHeaders.delete('location');
  }
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
