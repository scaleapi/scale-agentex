import type { ProcurementEvent } from '@/lib/types';

export function isProcurementEventData(
  data: unknown
): data is ProcurementEvent {
  return (
    data !== null &&
    typeof data === 'object' &&
    'event_type' in data &&
    'item' in data
  );
}

export function parseProcurementEventFromText(
  text: string
): ProcurementEvent | null {
  try {
    const parsed = JSON.parse(text);
    return isProcurementEventData(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
