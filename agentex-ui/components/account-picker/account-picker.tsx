'use client';

import { useCallback, useEffect, useMemo } from 'react';

import { useQueryClient } from '@tanstack/react-query';
import { Building2 } from 'lucide-react';

import { useAgentexClient } from '@/components/providers';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useUserInfo, userInfoKey } from '@/hooks/use-user-info';
import { cn } from '@/lib/utils';

export type AccountPickerProps = {
  className?: string;
  collapsed?: boolean;
};

/**
 * Current-account selector, driven by the `account_id` query param (the BFF turns it into
 * the `x-selected-account-id` header). Bootstraps to the first account when the param is
 * missing/stale — the API can't resolve a principal without it.
 */
export function AccountPicker({
  className,
  collapsed = false,
}: AccountPickerProps) {
  const { accountsEnabled, selectedAccountId, setSelectedAccountId } =
    useAgentexClient();
  const queryClient = useQueryClient();
  const { data, isLoading } = useUserInfo(accountsEnabled);
  const profiles = useMemo(() => data?.access_profiles ?? [], [data]);
  const selectedId = selectedAccountId ?? undefined;

  // Reset (not invalidate) account-scoped data on switch: invalidate keeps the old data
  // cached during refetch, briefly showing the previous account's agents. user-info is
  // preserved — the account list doesn't change on switch.
  const resetAccountScoped = useCallback(
    () =>
      queryClient.resetQueries({
        predicate: q => q.queryKey[0] !== userInfoKey[0],
      }),
    [queryClient]
  );
  const onAccountChange = useCallback(
    (id: string) => {
      if (id === selectedId) return;
      setSelectedAccountId(id);
      void resetAccountScoped();
    },
    [selectedId, setSelectedAccountId, resetAccountScoped]
  );

  // Default to the first account when the URL has no valid account_id (fixes the
  // "no account → 401" first load). `replace` so it doesn't add a history entry.
  useEffect(() => {
    if (profiles.length === 0) return;
    const valid =
      selectedId !== undefined &&
      profiles.some(p => p.account.id === selectedId);
    if (valid) return;
    const first = profiles[0];
    if (!first) return;
    setSelectedAccountId(first.account.id, true);
    void resetAccountScoped();
  }, [profiles, selectedId, setSelectedAccountId, resetAccountScoped]);

  if (!accountsEnabled) return null;

  // Size-9 collapsed-rail tile — shared by the loading placeholder (muted) and the
  // single-account display (solid).
  const iconTile = (opts?: { muted?: boolean; title?: string | undefined }) => (
    <div
      title={opts?.title}
      className={cn('flex size-9 items-center justify-center', className)}
    >
      <Building2
        className={cn(
          'size-5 shrink-0',
          opts?.muted ? 'text-muted-foreground' : 'text-foreground'
        )}
      />
    </div>
  );

  // Loading: a disabled, empty picker (icon only) rather than a skeleton — keeps the row stable.
  if (isLoading) {
    return collapsed ? (
      iconTile({ muted: true })
    ) : (
      <Select disabled>
        <SelectTrigger
          aria-label="Account"
          className={cn('w-full gap-2 rounded-md font-medium', className)}
        >
          <span className="flex flex-1 items-center gap-2 overflow-hidden text-left">
            <Building2 className="text-muted-foreground size-5 shrink-0" />
          </span>
        </SelectTrigger>
      </Select>
    );
  }

  if (profiles.length === 0) return null;

  const current = profiles.find(p => p.account.id === selectedId);
  const single = profiles.length === 1;
  const options = (
    <SelectContent>
      {profiles.map(p => (
        <SelectItem key={p.account.id} value={p.account.id}>
          {p.account.name}
        </SelectItem>
      ))}
    </SelectContent>
  );

  if (collapsed) {
    // Single → static icon; multiple → icon-only trigger (dropdown pops out beside the rail).
    if (single) return iconTile({ title: current?.account.name });
    return (
      <Select value={selectedId ?? ''} onValueChange={onAccountChange}>
        <SelectTrigger
          aria-label="Account"
          className={cn(
            'hover:bg-muted size-9 justify-center rounded-md border-0 bg-transparent p-0 shadow-none focus-visible:ring-0 [&>svg:last-child]:hidden',
            className
          )}
        >
          <Building2 className="text-foreground size-5 shrink-0" />
        </SelectTrigger>
        {options}
      </Select>
    );
  }

  // Single account: no switcher, just static context (matches the New Chat button).
  if (single) {
    return (
      <div
        className={cn(
          'text-foreground flex items-center gap-2 p-2 text-sm font-medium select-none',
          className
        )}
      >
        <Building2 className="size-5 shrink-0" />
        <span className="truncate">{current?.account.name}</span>
      </div>
    );
  }

  return (
    <Select value={selectedId ?? ''} onValueChange={onAccountChange}>
      <SelectTrigger
        className={cn('w-full gap-2 rounded-md font-medium', className)}
        aria-label="Account"
      >
        {/* Wrap icon + value in a flex-1 span so the value stays left-aligned
            (icon | value … chevron) instead of centered by justify-between. */}
        <span className="flex flex-1 items-center gap-2 overflow-hidden text-left">
          <Building2 className="text-foreground size-5 shrink-0" />
          <SelectValue placeholder="Select account" />
        </span>
      </SelectTrigger>
      {options}
    </Select>
  );
}
