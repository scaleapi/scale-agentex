import { describe, it, expect } from 'vitest';

import {
  isProcurementEventData,
  parseProcurementEventFromText,
} from '@/lib/procurement-utils';

describe('isProcurementEventData', () => {
  it('returns true for valid procurement event objects', () => {
    const validEvent = {
      event_type: 'Submittal_Approved',
      item: 'Steel beams',
    };
    expect(isProcurementEventData(validEvent)).toBe(true);
  });

  it('returns true for procurement events with additional fields', () => {
    const eventWithExtras = {
      event_type: 'Shipment_Departed_Factory',
      item: 'Concrete blocks',
      eta: '2024-12-01',
      date_departed: '2024-11-15',
      document_url: 'https://example.com/doc.pdf',
      document_name: 'Shipping Manifest',
      location_address: '123 Factory St',
    };
    expect(isProcurementEventData(eventWithExtras)).toBe(true);
  });

  it('returns false when event_type is missing', () => {
    const missingEventType = {
      item: 'Steel beams',
    };
    expect(isProcurementEventData(missingEventType)).toBe(false);
  });

  it('returns false when item is missing', () => {
    const missingItem = {
      event_type: 'Submittal_Approved',
    };
    expect(isProcurementEventData(missingItem)).toBe(false);
  });

  it('returns false for null', () => {
    expect(isProcurementEventData(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isProcurementEventData(undefined)).toBe(false);
  });

  it('returns false for strings', () => {
    expect(isProcurementEventData('not an object')).toBe(false);
  });

  it('returns false for numbers', () => {
    expect(isProcurementEventData(123)).toBe(false);
  });

  it('returns false for booleans', () => {
    expect(isProcurementEventData(true)).toBe(false);
  });

  it('returns false for arrays', () => {
    expect(isProcurementEventData([])).toBe(false);
    expect(isProcurementEventData([{ event_type: 'test', item: 'test' }])).toBe(
      false
    );
  });

  it('returns false for empty objects', () => {
    expect(isProcurementEventData({})).toBe(false);
  });

  it('returns false for objects with only one required field', () => {
    expect(isProcurementEventData({ event_type: 'test' })).toBe(false);
    expect(isProcurementEventData({ item: 'test' })).toBe(false);
  });
});

describe('parseProcurementEventFromText', () => {
  it('returns parsed event for valid JSON string', () => {
    const jsonString = JSON.stringify({
      event_type: 'Submittal_Approved',
      item: 'Steel beams',
    });
    const result = parseProcurementEventFromText(jsonString);
    expect(result).toEqual({
      event_type: 'Submittal_Approved',
      item: 'Steel beams',
    });
  });

  it('returns parsed event for JSON with all optional fields', () => {
    const jsonString = JSON.stringify({
      event_type: 'Shipment_Arrived_Site',
      item: 'Concrete',
      eta: '2024-12-01',
      date_arrived: '2024-11-20',
      inspection_date: '2024-11-21',
      document_url: 'https://example.com/doc.pdf',
      document_name: 'Arrival Certificate',
      location_address: '456 Site Ave',
    });
    const result = parseProcurementEventFromText(jsonString);
    expect(result).toMatchObject({
      event_type: 'Shipment_Arrived_Site',
      item: 'Concrete',
      eta: '2024-12-01',
      date_arrived: '2024-11-20',
    });
  });

  it('returns null for invalid JSON string', () => {
    const invalidJson = '{ not valid json }';
    expect(parseProcurementEventFromText(invalidJson)).toBe(null);
  });

  it('returns null for JSON missing event_type', () => {
    const jsonString = JSON.stringify({
      item: 'Steel beams',
      other_field: 'value',
    });
    expect(parseProcurementEventFromText(jsonString)).toBe(null);
  });

  it('returns null for JSON missing item', () => {
    const jsonString = JSON.stringify({
      event_type: 'Submittal_Approved',
      other_field: 'value',
    });
    expect(parseProcurementEventFromText(jsonString)).toBe(null);
  });

  it('returns null for valid JSON primitive values', () => {
    expect(parseProcurementEventFromText('"string"')).toBe(null);
    expect(parseProcurementEventFromText('123')).toBe(null);
    expect(parseProcurementEventFromText('true')).toBe(null);
    expect(parseProcurementEventFromText('null')).toBe(null);
  });

  it('returns null for JSON arrays', () => {
    const jsonArray = JSON.stringify([{ event_type: 'test', item: 'test' }]);
    expect(parseProcurementEventFromText(jsonArray)).toBe(null);
  });

  it('returns null for empty JSON object', () => {
    const emptyObject = JSON.stringify({});
    expect(parseProcurementEventFromText(emptyObject)).toBe(null);
  });

  it('returns null for empty string', () => {
    expect(parseProcurementEventFromText('')).toBe(null);
  });

  it('returns null for malformed JSON', () => {
    expect(parseProcurementEventFromText('{')).toBe(null);
    expect(parseProcurementEventFromText('undefined')).toBe(null);
    expect(parseProcurementEventFromText('NaN')).toBe(null);
  });

  it('handles JSON with extra whitespace', () => {
    const jsonString = `
      {
        "event_type": "Inspection_Passed",
        "item": "Electrical wiring"
      }
    `;
    const result = parseProcurementEventFromText(jsonString);
    expect(result).toEqual({
      event_type: 'Inspection_Passed',
      item: 'Electrical wiring',
    });
  });

  it('handles JSON with unicode characters', () => {
    const jsonString = JSON.stringify({
      event_type: 'Submittal_Approved',
      item: 'Matériaux de construction 🏗️',
    });
    const result = parseProcurementEventFromText(jsonString);
    expect(result).toMatchObject({
      event_type: 'Submittal_Approved',
      item: 'Matériaux de construction 🏗️',
    });
  });
});
