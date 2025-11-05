import { NextRequest, NextResponse } from 'next/server';

import Database from 'better-sqlite3';

import { ScheduleData, ProcurementItem, TaskDataTables } from '@/lib/types';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
): Promise<NextResponse<TaskDataTables | { error: string }>> {
  try {
    const { taskId } = await params;

    const dbPath = process.env.NEXT_PUBLIC_SQLITE_DB_PATH;

    if (!dbPath) {
      return NextResponse.json(
        { error: 'NEXT_PUBLIC_SQLITE_DB_PATH environment variable not set' },
        { status: 500 }
      );
    }

    const db = new Database(dbPath, { readonly: true });

    try {
      const scheduleQuery = db.prepare(`
        SELECT workflow_id, project_name, project_start_date, project_end_date,
               schedule_json, created_at, updated_at
        FROM master_construction_schedule
        WHERE workflow_id = ?
      `);
      const schedule = scheduleQuery.get(taskId) as ScheduleData | undefined;

      const procurementQuery = db.prepare(`
        SELECT workflow_id, item, status, eta, date_arrived,
               purchase_order_id, created_at, updated_at
        FROM procurement_items
        WHERE workflow_id = ?
        ORDER BY created_at DESC
      `);
      const procurementItems = procurementQuery.all(
        taskId
      ) as ProcurementItem[];

      return NextResponse.json({
        schedule: schedule || null,
        procurement_items: procurementItems,
      });
    } finally {
      db.close();
    }
  } catch (error) {
    console.error('Error querying SQLite database:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
