import { NextResponse } from 'next/server';

export function GET(): NextResponse<{ status: string }> {
  return NextResponse.json({ status: 'ok' }, { status: 200 });
}
