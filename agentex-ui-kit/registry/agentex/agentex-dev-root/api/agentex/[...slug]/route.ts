import { handleRequest } from "@/registry/agentex/agentex-dev-root/api/agentex/[...slug]/handlers";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string[] }> }
): Promise<NextResponse> {
  const [{ slug }, headersList] = await Promise.all([params, headers()]);
  const { searchParams } = request.nextUrl;
  const { body } = request;

  const { response, error } = await handleRequest(
    "GET",
    slug,
    headersList,
    searchParams,
    body,
    request.signal
  );

  if (response === null) {
    return notFound();
  }

  if (error !== undefined) {
    return new NextResponse(error, { status: 400 });
  }

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string[] }> }
): Promise<NextResponse> {
  const [{ slug }, headersList] = await Promise.all([params, headers()]);
  const { searchParams } = request.nextUrl;
  const { body } = request;

  const { response, error } = await handleRequest(
    "POST",
    slug,
    headersList,
    searchParams,
    body,
    request.signal
  );

  if (response === null) {
    return notFound();
  }

  if (error !== undefined) {
    return new NextResponse(error, { status: 400 });
  }

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
