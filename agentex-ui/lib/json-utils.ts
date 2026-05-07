import type { JsonValue } from '@/lib/types';

export type JsonObject = { [key: string]: JsonValue };

export function serializeValue(data: JsonValue): string {
  if (typeof data === 'object' && data !== null) {
    return JSON.stringify(data, null, 2);
  }
  if (typeof data === 'string') {
    return data;
  }
  return String(data);
}

export function parseJsonObject(input: string): JsonObject {
  let parsedValue: unknown;
  try {
    parsedValue = JSON.parse(input) as unknown;
  } catch (error) {
    throw new Error('Invalid JSON', { cause: error });
  }

  if (
    parsedValue === null ||
    typeof parsedValue !== 'object' ||
    Array.isArray(parsedValue)
  ) {
    throw new Error('Expected a JSON object');
  }

  return parsedValue as JsonObject;
}

export function parseOptionalJsonObject(input: string): JsonObject | undefined {
  if (!input.trim()) {
    return undefined;
  }

  return parseJsonObject(input);
}
