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

function call(traceId: string, init?: RequestInit, search = '') {
  return GET(
    new Request(`http://ui.local/api/traces/${traceId}/spans${search}`, init),
    { params: Promise.resolve({ traceId }) }
  );
}

function upstreamURL(fetchMock: ReturnType<typeof vi.fn>) {
  return new URL(fetchMock.mock.calls[0]![0] as string);
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
      'https://sgp.example/api/v5/spans/search?limit=100&sort_by=start_timestamp&sort_order=asc&allow_short_pages=true'
    );
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ trace_ids: ['t1'] });
    expect(new Headers(init.headers).get('authorization')).toBe(
      'Bearer server-side'
    );
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it('answers 499 when the browser aborts before the platform replies', async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        const signal = init.signal as AbortSignal;
        return new Promise<Response>((_resolve, reject) => {
          if (signal.aborted) reject(signal.reason);
          signal.addEventListener('abort', () => reject(signal.reason));
        });
      })
    );

    const pending = call('t1', { signal: controller.signal });
    controller.abort();
    const res = await pending;

    expect(res.status).toBe(499);
  });

  it('starts the search window at the task creation time and leaves it open-ended', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('{"items":[]}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const from = '2026-01-01T00:00:00.000Z';

    await call('t1', undefined, `?from=${encodeURIComponent(from)}`);

    const params = upstreamURL(fetchMock).searchParams;
    expect(Date.parse(params.get('from_ts')!)).toBe(
      Date.parse(from) - 5 * 60 * 1000
    );
    expect(params.has('to_ts')).toBe(false);
  });

  it('passes the platform truncation of a window wider than 90 days through', async () => {
    const from = new Date(Date.now() - 200 * 24 * 60 * 60 * 1000).toISOString();
    const effectiveFrom = new Date(
      Date.now() - 90 * 24 * 60 * 60 * 1000
    ).toISOString();
    const page = {
      items: [{ id: 's1', trace_id: 't1' }],
      has_more: false,
      window_truncated: true,
      effective_from_ts: effectiveFrom,
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(page), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      )
    );

    const res = await call(
      't1',
      undefined,
      `?from=${encodeURIComponent(from)}`
    );

    expect(await res.json()).toEqual(page);
  });

  it('sends no window without a creation time', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('{"items":[]}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await call('t1');

    const params = upstreamURL(fetchMock).searchParams;
    expect(params.has('from_ts')).toBe(false);
    expect(params.has('to_ts')).toBe(false);
  });

  it('rejects a creation time that is not a timestamp', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const res = await call('t1', undefined, '?from=yesterday');

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
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
