import { redirect } from 'next/navigation';

/**
 * Catches direct/stale hits on /login (e.g. logout or an SDK sending the browser
 * to `/login?redirect_url=…`) and forwards to the server-side auto-signin handler
 * so sign-in returns the user to their destination.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ redirect_url?: string }>;
}) {
  const { redirect_url } = await searchParams;
  redirect(
    `/api/auth/auto-signin?redirect_url=${encodeURIComponent(redirect_url ?? '/')}`
  );
}
