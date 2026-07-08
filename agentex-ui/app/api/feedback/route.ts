import { NextResponse } from 'next/server';

import { applyBffCredentials, SGP_BASE_URL } from '@/app/api/_lib/bff';

type FeedbackRequestBody = {
  traceId: string;
  messageId: string;
  taskId: string;
  input: string;
  output: string;
  approval: 'approved' | 'rejected';
  comment?: string;
  agentName?: string;
  agentId?: string;
  agentAcpType?: string;
};

async function sgpPost<T>(
  path: string,
  body: unknown,
  headers: Headers
): Promise<T> {
  const res = await fetch(`${SGP_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`SGP ${path} returned ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function POST(request: Request) {
  if (!SGP_BASE_URL) {
    return NextResponse.json(
      {
        error: 'SGP feedback is not configured. Set SGP_API_URL.',
      },
      { status: 503 }
    );
  }

  let body: FeedbackRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const {
    traceId,
    messageId,
    taskId,
    input,
    output,
    approval,
    comment,
    agentName,
    agentId,
    agentAcpType,
  } = body;

  if (!traceId || !messageId || !taskId || !approval) {
    return NextResponse.json(
      {
        error: 'Missing required fields: traceId, messageId, taskId, approval',
      },
      { status: 400 }
    );
  }

  if (approval !== 'approved' && approval !== 'rejected') {
    return NextResponse.json(
      { error: 'approval must be "approved" or "rejected"' },
      { status: 400 }
    );
  }

  // Same server-side credentials the agentex proxy forwards (access token or cookies,
  // plus x-selected-account-id) — the client never sends them.
  const sgpHeaders = new Headers({ 'Content-Type': 'application/json' });
  await applyBffCredentials(request, sgpHeaders);
  const now = new Date().toISOString();

  try {
    const span = await sgpPost<{ id: string }>(
      '/v5/spans',
      {
        name: 'user-feedback',
        trace_id: traceId,
        start_timestamp: now,
        end_timestamp: now,
        input: { user_message: input },
        output: { agent_message: output },
        metadata: {
          message_id: messageId,
          task_id: taskId,
          __source__: 'agentex',
          ...(agentName ? { __agent_name__: agentName } : {}),
          ...(agentId ? { __agent_id__: agentId } : {}),
          ...(agentAcpType ? { __acp_type__: agentAcpType } : {}),
        },
        status: 'SUCCESS',
        type: 'STANDALONE',
      },
      sgpHeaders
    );

    const assessments = await Promise.all([
      sgpPost<{ assessment_id: string }>(
        '/v5/span-assessments',
        {
          assessment_type: 'approval',
          span_id: span.id,
          trace_id: traceId,
          approval,
        },
        sgpHeaders
      ),
      ...(comment
        ? [
            sgpPost<{ assessment_id: string }>(
              '/v5/span-assessments',
              {
                assessment_type: 'comment',
                span_id: span.id,
                trace_id: traceId,
                comment,
              },
              sgpHeaders
            ),
          ]
        : []),
    ]);

    return NextResponse.json(
      {
        spanId: span.id,
        assessmentIds: assessments.map(a => a.assessment_id),
      },
      { status: 201 }
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.error('SGP feedback error:', error);
    return NextResponse.json(
      { error: `Failed to create feedback in SGP: ${message}` },
      { status: 502 }
    );
  }
}
