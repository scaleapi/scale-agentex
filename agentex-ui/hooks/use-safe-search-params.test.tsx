import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  ScheduleScope,
  SearchParamKey,
  useSafeSearchParams,
} from './use-safe-search-params';

// Router spies + a mutable snapshot the mocked `useSearchParams` returns. Created via
// vi.hoisted so the hoisted vi.mock factory can reference them.
const mocks = vi.hoisted(() => ({
  push: vi.fn<(url: string) => void>(),
  replace: vi.fn<(url: string) => void>(),
  snapshot: new URLSearchParams(''),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  usePathname: () => '/',
  useSearchParams: () => mocks.snapshot,
}));

function setLiveUrl(search: string) {
  window.history.replaceState(null, '', `${window.location.origin}/${search}`);
}

function pushedQuery() {
  expect(mocks.push).toHaveBeenCalledTimes(1);
  const url = mocks.push.mock.calls[0]![0];
  return new URLSearchParams(url.split('?')[1] ?? '');
}

afterEach(() => {
  mocks.push.mockClear();
  mocks.replace.mockClear();
});

describe('useSafeSearchParams.updateParams', () => {
  it('merges against the live URL, not a stale snapshot (no write-clobber)', () => {
    // The live URL already reflects a committed account switch: new account, task_id dropped.
    setLiveUrl('?account_id=new&agent_name=dua-agent');
    // But the React snapshot still shows the pre-switch state (the lag that caused the bug).
    mocks.snapshot = new URLSearchParams(
      'account_id=old&task_id=T&agent_name=dua-agent'
    );

    const { result } = renderHook(() => useSafeSearchParams());
    // A second writer (the agent-validation effect) clears only agent_name.
    result.current.updateParams({ [SearchParamKey.AGENT_NAME]: null });

    // It must build from the live URL: keep account_id=new, leave task_id dropped — not
    // resurrect account_id=old / task_id=T from the stale snapshot.
    const qs = pushedQuery();
    expect(qs.get('account_id')).toBe('new');
    expect(qs.get('task_id')).toBeNull();
    expect(qs.get('agent_name')).toBeNull();
  });

  it('sets, deletes, and preserves unlisted params in one update', () => {
    setLiveUrl('?account_id=acc&agent_name=keep');
    mocks.snapshot = new URLSearchParams('account_id=acc&agent_name=keep');

    const { result } = renderHook(() => useSafeSearchParams());
    result.current.updateParams({
      [SearchParamKey.TASK_ID]: 'new-task',
      [SearchParamKey.AGENT_NAME]: null,
    });

    const qs = pushedQuery();
    expect(qs.get('task_id')).toBe('new-task'); // set
    expect(qs.get('agent_name')).toBeNull(); // deleted
    expect(qs.get('account_id')).toBe('acc'); // preserved (unlisted)
  });

  it('uses router.replace when replace=true', () => {
    setLiveUrl('?account_id=acc');
    mocks.snapshot = new URLSearchParams('account_id=acc');

    const { result } = renderHook(() => useSafeSearchParams());
    result.current.updateParams({ [SearchParamKey.TASK_ID]: 'x' }, true);

    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.replace).toHaveBeenCalledTimes(1);
    expect(mocks.replace.mock.calls[0]![0]).toContain('task_id=x');
  });
});

describe('useSafeSearchParams.scheduleScope', () => {
  it('parses all scope and defaults every other value to current', () => {
    mocks.snapshot = new URLSearchParams('schedule_scope=all');
    const { result, rerender } = renderHook(() => useSafeSearchParams());
    expect(result.current.scheduleScope).toBe(ScheduleScope.ALL);

    mocks.snapshot = new URLSearchParams('schedule_scope=unexpected');
    rerender();
    expect(result.current.scheduleScope).toBe(ScheduleScope.CURRENT);
  });
});
