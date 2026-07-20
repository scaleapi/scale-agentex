import { afterEach, describe, expect, it, vi } from 'vitest';

import { parseBooleanEnv } from './env-utils';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('parseBooleanEnv', () => {
  it.each(['true', 'TRUE', ' 1 '])('parses %s as true', value => {
    expect(parseBooleanEnv(value, 'FEATURE_FLAG')).toBe(true);
  });

  it.each(['false', 'FALSE', ' 0 '])('parses %s as false', value => {
    expect(parseBooleanEnv(value, 'FEATURE_FLAG')).toBe(false);
  });

  it('defaults missing values to false without warning', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    expect(parseBooleanEnv(undefined, 'FEATURE_FLAG')).toBe(false);
    expect(warn).not.toHaveBeenCalled();
  });

  it('warns and fails closed for invalid values', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    expect(parseBooleanEnv('enabled', 'FEATURE_FLAG')).toBe(false);
    expect(warn).toHaveBeenCalledWith(
      'Invalid FEATURE_FLAG value "enabled"; defaulting to false'
    );
  });
});
