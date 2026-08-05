import { authEnabled, handlers } from '@/auth';

// No NextAuth routes in default mode — 404 rather than the provider-less handler's 500.
const notFound = () => new Response(null, { status: 404 });

export const GET = authEnabled ? handlers.GET : notFound;
export const POST = authEnabled ? handlers.POST : notFound;
