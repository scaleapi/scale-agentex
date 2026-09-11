import { NextResponse } from 'next/server';

import { applyBffCredentials, SGP_BASE_URL } from '@/app/api/_lib/bff';

/**
 * Scoped BFF proxy for one trace's spans, read from the platform's span search with the
 * credentials attached server-side. Only this path is exposed, not a catch-all, so the
 * browser can't reach arbitrary platform endpoints with those credentials.
 */
export const dynamic = 'force-dynamic';

// The platform caps a search page at this size, and the sidebar shows the first page.
const PAGE_SIZE = 100;

export async function GET(
  request: Request,
  ctx: { params: Promise<{ traceId: string }> }
): Promise<Response> {
  if (!SGP_BASE_URL) {
    return NextResponse.json(
      { error: 'SGP traces are not configured. Set SGP_API_URL.' },
      { status: 503 }
    );
  }

  const { traceId } = await ctx.params;
  const headers = new Headers({
    'Content-Type': 'application/json',
    accept: 'application/json',
  });
  await applyBffCredentials(request, headers);

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    sort_by: 'start_timestamp',
    sort_order: 'asc',
  });
  const upstream = await fetch(`${SGP_BASE_URL}/v5/spans/search?${query}`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ trace_ids: [traceId] }),
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': 'application/json' },
  });
}
