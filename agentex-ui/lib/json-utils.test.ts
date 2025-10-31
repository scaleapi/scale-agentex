import { describe, it, expect } from 'vitest';

import { serializeValue } from '@/lib/json-utils';
import type { JsonValue } from '@/lib/types';

describe('serializeValue', () => {
  it('serializes objects with pretty printing', () => {
    const data = { foo: 'bar', baz: 123 };
    const result = serializeValue(data);
    expect(result).toBe('{\n  "foo": "bar",\n  "baz": 123\n}');
  });

  it('serializes arrays with pretty printing', () => {
    const data = [1, 2, 3];
    const result = serializeValue(data);
    expect(result).toBe('[\n  1,\n  2,\n  3\n]');
  });

  it('returns string as-is', () => {
    const data = 'hello world';
    const result = serializeValue(data);
    expect(result).toBe('hello world');
  });

  it('converts number to string', () => {
    const data = 42;
    const result = serializeValue(data);
    expect(result).toBe('42');
  });

  it('converts boolean to string', () => {
    expect(serializeValue(true)).toBe('true');
    expect(serializeValue(false)).toBe('false');
  });

  it('converts null to string', () => {
    const data = null;
    const result = serializeValue(data);
    expect(result).toBe('null');
  });

  it('handles nested objects', () => {
    const data = {
      user: {
        name: 'John',
        age: 30,
      },
      tags: ['tag1', 'tag2'],
    };
    const result = serializeValue(data);
    expect(result).toContain('"user"');
    expect(result).toContain('"name": "John"');
    expect(result).toContain('"tags"');
  });

  it('handles empty objects', () => {
    const data = {};
    const result = serializeValue(data);
    expect(result).toBe('{}');
  });

  it('handles empty arrays', () => {
    const data: JsonValue[] = [];
    const result = serializeValue(data);
    expect(result).toBe('[]');
  });

  it('handles empty strings', () => {
    const data = '';
    const result = serializeValue(data);
    expect(result).toBe('');
  });

  it('handles zero', () => {
    const data = 0;
    const result = serializeValue(data);
    expect(result).toBe('0');
  });
});
