import { afterEach, describe, expect, it, vi } from 'vitest';

import { GET } from './route';

const bff = vi.hoisted(() => ({
  baseURL: 'https://sgp.example/api' as string | undefined,
  applyBffCredentials: vi.fn(async (_req: Request, headers: Headers) => {
    headers.set('authorization', 'Bearer server-side');
  }),
}));

vi.mock('@/app/api/_lib/bff', () => ({
  get SGP_BASE_URL() {
    return bff.baseURL;
  },
  applyBffCredentials: bff.applyBffCredentials,
}));

function call(traceId: string) {
  return GET(new Request(`http://ui.local/api/traces/${traceId}/spans`), {
    params: Promise.resolve({ traceId }),
  });
}

describe('GET /api/traces/[traceId]/spans', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    bff.baseURL = 'https://sgp.example/api';
  });

  it('searches the platform for the trace with server-attached credentials', async () => {
    const page = { items: [{ id: 's1', trace_id: 't1' }], has_more: false };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(page), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const res = await call('t1');

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(page);
    expect(bff.applyBffCredentials).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(
      'https://sgp.example/api/v5/spans/search?limit=100&sort_by=start_timestamp&sort_order=asc'
    );
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ trace_ids: ['t1'] });
    expect(new Headers(init.headers).get('authorization')).toBe(
      'Bearer server-side'
    );
  });

  it('passes the upstream status through', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: 'forbidden' }), { status: 403 })
        )
    );

    const res = await call('t1');

    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ detail: 'forbidden' });
  });

  it('returns 503 when the platform API is not configured', async () => {
    bff.baseURL = undefined;
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const res = await call('t1');

    expect(res.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
