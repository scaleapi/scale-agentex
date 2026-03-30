import { NextResponse } from 'next/server';

import SGPClient from 'scale-gp';

type FeedbackRequestBody = {
  traceId: string;
  messageId: string;
  taskId: string;
  input: string;
  output: string;
  approval: 'approved' | 'rejected';
  comment?: string;
};

function getSGPClient(): SGPClient | null {
  const apiKey = process.env.SGP_API_KEY;
  const accountID = process.env.SGP_ACCOUNT_ID;
  const baseURL = process.env.SGP_API_URL;

  if (!apiKey || !accountID) {
    return null;
  }

  return new SGPClient({
    apiKey,
    accountID,
    ...(baseURL ? { baseURL } : {}),
  });
}

export async function POST(request: Request) {
  const client = getSGPClient();

  if (!client) {
    return NextResponse.json(
      {
        error:
          'SGP feedback is not configured. Set SGP_API_KEY and SGP_ACCOUNT_ID.',
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

  const { traceId, messageId, taskId, input, output, approval, comment } = body;

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

  try {
    const now = new Date().toISOString();

    const span = await client.spans.create({
      name: 'user-feedback',
      trace_id: traceId,
      start_timestamp: now,
      end_timestamp: now,
      input: { user_message: input },
      output: { agent_message: output },
      metadata: {
        source: 'agentex-ui',
        message_id: messageId,
        task_id: taskId,
      },
      status: 'SUCCESS',
      type: 'STANDALONE',
    });

    // spanAssessments resource not yet in published SDK — use generic post
    const assessment = await client.post<{
      assessment_id: string;
      span_id: string;
      trace_id: string;
    }>('/v5/span-assessments', {
      body: {
        assessment_type: 'approval',
        span_id: span.id,
        trace_id: traceId,
        approval,
        ...(comment ? { comment } : {}),
      },
    });

    return NextResponse.json(
      { spanId: span.id, assessmentId: assessment.assessment_id },
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
