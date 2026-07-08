import { useQuery } from '@tanstack/react-query';

/** A member account the caller can access (from the platform's /user-info). */
export type AccessProfile = {
  id: string;
  role?: string;
  account: {
    id: string;
    name: string;
    organization_id?: string | null;
    status?: string;
  };
};

type UserInfo = { access_profiles: AccessProfile[] };

export const userInfoKey = ['user-info'] as const;

/**
 * Fetches the caller's accounts (access_profiles) via the scoped `/api/user-info` BFF
 * proxy, to bootstrap / switch the selected account. `enabled` gates the fetch (off when
 * the platform API isn't configured).
 */
export function useUserInfo(enabled: boolean) {
  return useQuery({
    queryKey: userInfoKey,
    enabled,
    queryFn: async (): Promise<UserInfo> => {
      const res = await fetch('/api/user-info', { credentials: 'include' });
      if (!res.ok) throw new Error(`user-info: ${res.status}`);
      return res.json();
    },
    // The account list is stable for the session — fetch once, don't refetch on remount
    // (e.g. the account_id navigation) or focus.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
