import type { JsonValue } from '@/lib/types';

export function serializeValue(data: JsonValue): string {
  if (typeof data === 'object' && data !== null) {
    return JSON.stringify(data, null, 2);
  }
  if (typeof data === 'string') {
    return data;
  }
  return String(data);
}
