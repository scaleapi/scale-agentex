import { NextResponse } from 'next/server';

import { applyBffCredentials, SGP_BASE_URL } from '@/app/api/_lib/bff';

/**
 * Scoped BFF proxy for one trace's spans, read from the platform's span search with the
 * credentials attached server-side. Only this path is exposed, not a catch-all, so the
 * browser can't reach arbitrary platform endpoints with those credentials.
 */
export const dynamic = 'force-dynamic';

// The sidebar shows one page and reports the rest through has_more.
const PAGE_SIZE = 100;
// Start at the task's creation and leave the end open: the platform clamps a window wider than
// 90 days to its newest 90 and reports that through window_truncated.
const SKEW_MS = 5 * 60 * 1000;

function searchWindow(from: string | null): Record<string, string> | null {
  if (from === null) return {};
  const start = Date.parse(from);
  if (Number.isNaN(start)) return null;
  return { from_ts: new Date(start - SKEW_MS).toISOString() };
}

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
  const window = searchWindow(new URL(request.url).searchParams.get('from'));
  if (window === null) {
    return NextResponse.json(
      { error: 'from must be an ISO timestamp' },
      { status: 400 }
    );
  }
  const headers = new Headers({
    'Content-Type': 'application/json',
    accept: 'application/json',
  });
  await applyBffCredentials(request, headers);

  const query = new URLSearchParams({
    limit: String(PAGE_SIZE),
    sort_by: 'start_timestamp',
    sort_order: 'asc',
    // Over the byte budget the platform shortens the page instead of refusing it.
    allow_short_pages: 'true',
    ...window,
  });
  let upstream: Response;
  try {
    upstream = await fetch(`${SGP_BASE_URL}/v5/spans/search?${query}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ trace_ids: [traceId] }),
      signal: request.signal,
    });
  } catch (error) {
    // A browser that navigated away aborts the request, and the abort reason is what the
    // fetch rejects with, so the same identity check the Agentex proxy uses applies here.
    if (error === request.signal.reason) {
      return new Response(null, { status: 499 });
    }
    throw error;
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': 'application/json' },
  });
}
