export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type ScheduleData = {
  workflow_id: string;
  project_name: string;
  project_start_date: string;
  project_end_date: string;
  schedule_json: string;
  created_at: string;
  updated_at: string;
};

export type ProcurementItem = {
  workflow_id: string;
  item: string;
  status: string;
  eta: string | null;
  date_arrived: string | null;
  purchase_order_id: string | null;
  created_at: string;
  updated_at: string;
};

export type EventType =
  | 'Submittal_Approved'
  | 'Shipment_Departed_Factory'
  | 'Shipment_Arrived_Site'
  | 'Inspection_Passed'
  | 'Inspection_Failed';

export type ProcurementEvent = {
  event_type: EventType;
  item: string;
  eta?: string;
  date_arrived?: string;
  date_departed?: string;
  inspection_date?: string;
  document_url?: string;
  document_name?: string;
  location_address?: string;
};

export type TaskDataTables = {
  schedule: ScheduleData | null;
  procurement_items: ProcurementItem[];
};

export type MapMetadata = {
  item?: string | undefined;
  deliveryDate?: string | undefined;
  dateDeparted?: string | undefined;
  eta?: string | undefined;
  eventType?: string | undefined;
};
