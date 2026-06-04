/**
 * Thin server-side SGP REST client. Lives in lib/ because it's called from
 * Next.js route handlers (app/api/...), not the browser — keeps the SGP
 * base URL + outgoing auth headers off the client bundle.
 */

const SGP_BASE_URL =
  process.env.NEXT_PUBLIC_SGP_API_URL ??
  (process.env.NEXT_PUBLIC_SGP_APP_URL
    ? `${process.env.NEXT_PUBLIC_SGP_APP_URL}/api`
    : undefined);

export type SGPClientError = {
  status: number;
  body: string;
};

export function isSGPConfigured(): boolean {
  return Boolean(SGP_BASE_URL);
}

export function sgpHeadersFromRequest(
  request: Request
): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const forwarded = [
    'cookie',
    'authorization',
    'x-api-key',
    'x-selected-account-id',
  ];
  for (const key of forwarded) {
    const value = request.headers.get(key);
    if (value) headers[key] = value;
  }

  // Server-side fallbacks: the browser fetch to /api/agent-configs carries no
  // SGP credentials, so when nothing was forwarded fall back to the API key +
  // account id configured for this UI instance. Forwarded headers (e.g. a real
  // logged-in SGP session) take precedence over the env defaults.
  if (!headers['x-api-key'] && process.env.SGP_API_KEY) {
    headers['x-api-key'] = process.env.SGP_API_KEY;
  }
  if (!headers['x-selected-account-id'] && process.env.SGP_ACCOUNT_ID) {
    headers['x-selected-account-id'] = process.env.SGP_ACCOUNT_ID;
  }

  return headers;
}

async function sgpFetch(
  path: string,
  init: RequestInit,
  headers: Record<string, string>
): Promise<Response> {
  if (!SGP_BASE_URL) {
    throw new Error(
      'SGP is not configured. Set NEXT_PUBLIC_SGP_API_URL or NEXT_PUBLIC_SGP_APP_URL.'
    );
  }
  return fetch(`${SGP_BASE_URL}${path}`, { ...init, headers });
}

async function parseOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    const err: SGPClientError = { status: res.status, body };
    throw err;
  }
  return res.json() as Promise<T>;
}

// ----- Agent configs --------------------------------------------------------

export type AgentConfig = {
  object: 'agent_config';
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  harness: string;
  allowed_tools: string[];
  model: string;
  created_at: string;
  updated_at: string;
};

export type AgentConfigListResponse = {
  items: AgentConfig[];
  // SGP paginated list may include cursors/total — keeping loose to avoid
  // over-fitting the type to one shape.
  [k: string]: unknown;
};

export type CreateAgentConfigRequest = {
  name: string;
  description?: string;
  system_prompt: string;
  harness: string;
  allowed_tools: string[];
  model: string;
};

export type UpdateAgentConfigRequest = Partial<CreateAgentConfigRequest>;

export async function listAgentConfigs(
  request: Request
): Promise<AgentConfigListResponse> {
  const res = await sgpFetch(
    '/v5/agent_configs',
    { method: 'GET' },
    sgpHeadersFromRequest(request)
  );
  return parseOrThrow<AgentConfigListResponse>(res);
}

export async function createAgentConfig(
  request: Request,
  body: CreateAgentConfigRequest
): Promise<AgentConfig> {
  const res = await sgpFetch(
    '/v5/agent_configs',
    { method: 'POST', body: JSON.stringify(body) },
    sgpHeadersFromRequest(request)
  );
  return parseOrThrow<AgentConfig>(res);
}

export async function getAgentConfig(
  request: Request,
  id: string
): Promise<AgentConfig> {
  const res = await sgpFetch(
    `/v5/agent_configs/${encodeURIComponent(id)}`,
    { method: 'GET' },
    sgpHeadersFromRequest(request)
  );
  return parseOrThrow<AgentConfig>(res);
}

export async function updateAgentConfig(
  request: Request,
  id: string,
  body: UpdateAgentConfigRequest
): Promise<AgentConfig> {
  const res = await sgpFetch(
    `/v5/agent_configs/${encodeURIComponent(id)}`,
    { method: 'PATCH', body: JSON.stringify(body) },
    sgpHeadersFromRequest(request)
  );
  return parseOrThrow<AgentConfig>(res);
}

export async function deleteAgentConfig(
  request: Request,
  id: string
): Promise<void> {
  const res = await sgpFetch(
    `/v5/agent_configs/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    sgpHeadersFromRequest(request)
  );
  if (!res.ok) {
    const body = await res.text();
    const err: SGPClientError = { status: res.status, body };
    throw err;
  }
}
