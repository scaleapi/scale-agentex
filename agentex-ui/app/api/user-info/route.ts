import { NextResponse } from 'next/server';

import { applyBffCredentials, SGP_BASE_URL } from '@/app/api/_lib/bff';

/**
 * Scoped BFF proxy for the caller's accounts (access_profiles), used to bootstrap/switch
 * the selected account. Only this path is exposed — not a catch-all — so the browser can't
 * reach arbitrary platform endpoints with the server-attached credentials.
 */
export const dynamic = 'force-dynamic';

export async function GET(request: Request): Promise<Response> {
  if (!SGP_BASE_URL) {
    return NextResponse.json(
      { error: 'SGP is not configured. Set SGP_API_URL.' },
      { status: 503 }
    );
  }

  const headers = new Headers({ accept: 'application/json' });
  await applyBffCredentials(request, headers);
  const upstream = await fetch(`${SGP_BASE_URL}/user-info`, { headers });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': 'application/json' },
  });
}
