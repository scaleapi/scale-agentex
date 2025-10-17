import { useAppConfig } from '@/hooks/use-app-config';

export function useBackToSgpHref({
  sgpAccountID,
}: {
  sgpAccountID: string | null;
}): string | null {
  const { sgpAppURL } = useAppConfig();

  try {
    if (!sgpAccountID) {
      return null;
    }
    const url = new URL(sgpAppURL);
    // TODO: keep in sync with egp-annotation when this changes
    url.pathname = url.pathname.replace(/\/$/, '') + '/beta/build';
    url.searchParams.set('account_id', sgpAccountID);
    return url.toString();
  } catch {
    return null;
  }
}
