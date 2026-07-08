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

  // Refetch account-scoped data (agents, tasks, …) on an account change — but NOT
  // user-info: the account list itself doesn't change when you switch accounts.
  const refetchAccountScoped = useCallback(
    () =>
      queryClient.invalidateQueries({
        predicate: q => q.queryKey[0] !== userInfoKey[0],
      }),
    [queryClient]
  );
  const onAccountChange = useCallback(
    (id: string) => {
      if (id === selectedId) return;
      setSelectedAccountId(id);
      void refetchAccountScoped();
    },
    [selectedId, setSelectedAccountId, refetchAccountScoped]
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
    void refetchAccountScoped();
  }, [profiles, selectedId, setSelectedAccountId, refetchAccountScoped]);

  if (!accountsEnabled) return null;

  // A size-9 icon tile — the collapsed-rail footprint. Shared by the loading placeholder
  // (muted) and the single-account display (solid, with the name as a tooltip).
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

  // While accounts load, show a disabled, empty picker (icon only) instead of a skeleton
  // block — keeps the row stable and reads as a loading account selector.
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
    // Single account → static icon; multiple → an icon-only trigger whose dropdown pops
    // out beside the collapsed rail (Radix keeps it in view).
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

  // A single account needs no switcher — show it as static context, matching the New Chat
  // button's size + spacing (size-5 icon, p-2, medium weight).
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
