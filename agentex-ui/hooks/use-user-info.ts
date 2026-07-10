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

/** Caller's accounts (access_profiles) via /api/user-info; `enabled` off when unconfigured. */
export function useUserInfo(enabled: boolean) {
  return useQuery({
    queryKey: userInfoKey,
    enabled,
    queryFn: async (): Promise<UserInfo> => {
      const res = await fetch('/api/user-info', { credentials: 'include' });
      if (!res.ok) throw new Error(`user-info: ${res.status}`);
      return res.json();
    },
    // The account list is stable for the session — don't refetch on the account_id
    // navigation or window focus.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
