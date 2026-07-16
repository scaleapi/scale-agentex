import { NextResponse } from 'next/server';

import {
  createAgentConfig,
  isSGPConfigured,
  listAgentConfigs,
  type CreateAgentConfigRequest,
} from '@/lib/sgp-client';

function notConfigured() {
  return NextResponse.json(
    {
      error:
        'SGP is not configured. Set NEXT_PUBLIC_SGP_API_URL (e.g. http://localhost:5003/public) and restart the UI.',
    },
    { status: 503 }
  );
}

export async function GET(request: Request) {
  if (!isSGPConfigured()) return notConfigured();
  try {
    const data = await listAgentConfigs(request);
    return NextResponse.json(data);
  } catch (error) {
    return forwardError(error);
  }
}

export async function POST(request: Request) {
  if (!isSGPConfigured()) return notConfigured();

  let body: CreateAgentConfigRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }
  if (!body.name || !body.system_prompt || !body.harness || !body.model) {
    return NextResponse.json(
      { error: 'name, system_prompt, harness, model are required' },
      { status: 400 }
    );
  }

  try {
    const created = await createAgentConfig(request, {
      ...body,
      allowed_tools: body.allowed_tools ?? [],
    });
    return NextResponse.json(created, { status: 201 });
  } catch (error) {
    return forwardError(error);
  }
}

function forwardError(error: unknown) {
  if (
    typeof error === 'object' &&
    error &&
    'status' in error &&
    'body' in error
  ) {
    const e = error as { status: number; body: string };
    return NextResponse.json({ error: e.body }, { status: e.status });
  }
  const message = error instanceof Error ? error.message : 'Unknown error';
  return NextResponse.json({ error: message }, { status: 502 });
}
