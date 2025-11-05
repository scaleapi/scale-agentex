'use client';

import { useMemo, useEffect, useRef, useState } from 'react';

import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUpDown, Loader2, AlertCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { ProcurementItem, TaskDataTables } from '@/lib/types';
import { cn } from '@/lib/utils';

type RowChangeType = 'added' | 'updated' | 'deleted' | 'none';

type RowChangeState = {
  type: RowChangeType;
  timestamp: number;
};

type DataTableViewerProps = {
  data: TaskDataTables | null;
  isLoading: boolean;
  error: string | null;
  onRefresh?: () => void;
};

const procurementColumnHelper = createColumnHelper<ProcurementItem>();

const procurementColumns = [
  procurementColumnHelper.accessor('item', {
    header: ({ column }) => (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
      >
        Item
        <ArrowUpDown className="ml-2 h-4 w-4" />
      </Button>
    ),
    cell: info => <span className="font-medium">{info.getValue()}</span>,
  }),
  procurementColumnHelper.accessor('status', {
    header: ({ column }) => (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
      >
        Status
        <ArrowUpDown className="ml-2 h-4 w-4" />
      </Button>
    ),
    cell: info => {
      const status = info.getValue();
      const statusColors: Record<string, string> = {
        pending:
          'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
        in_progress:
          'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
        completed:
          'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
        delayed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
      };
      return (
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
            statusColors[status] ||
              'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
          )}
        >
          {status}
        </span>
      );
    },
  }),
  procurementColumnHelper.accessor('eta', {
    header: 'ETA',
    cell: info => {
      const value = info.getValue();
      return value ? new Date(value).toLocaleDateString() : '—';
    },
  }),
  procurementColumnHelper.accessor('date_arrived', {
    header: 'Date Arrived',
    cell: info => {
      const value = info.getValue();
      return value ? new Date(value).toLocaleDateString() : '—';
    },
  }),
  procurementColumnHelper.accessor('purchase_order_id', {
    header: 'PO ID',
    cell: info => info.getValue() || '—',
  }),
  procurementColumnHelper.accessor('updated_at', {
    header: ({ column }) => (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
      >
        Updated
        <ArrowUpDown className="ml-2 h-4 w-4" />
      </Button>
    ),
    cell: info => {
      const value = info.getValue();
      return new Date(value).toLocaleString();
    },
  }),
];

export function DataTableViewer({
  data,
  isLoading,
  error,
}: DataTableViewerProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowChanges, setRowChanges] = useState<Map<string, RowChangeState>>(
    new Map()
  );
  const [deletingRows, setDeletingRows] = useState<Set<string>>(new Set());
  const prevDataRef = useRef<ProcurementItem[]>([]);

  // Create merged display data that includes items being deleted at the end
  const displayItems = useMemo(() => {
    const current = data?.procurement_items || [];
    const deletedItems = prevDataRef.current.filter(
      prev =>
        !current.some(curr => curr.item === prev.item) &&
        deletingRows.has(prev.item)
    );
    return [...current, ...deletedItems];
  }, [data?.procurement_items, deletingRows]);

  const table = useReactTable({
    data: displayItems,
    columns: procurementColumns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: {
      sorting,
    },
  });

  const scheduleData = useMemo(() => {
    if (!data?.schedule?.schedule_json) return null;
    try {
      return JSON.parse(data.schedule.schedule_json);
    } catch {
      return null;
    }
  }, [data?.schedule?.schedule_json]);

  // Detect changes in procurement items
  useEffect(() => {
    if (!data?.procurement_items || isLoading) return;

    const currentItems = data.procurement_items;
    const previousItems = prevDataRef.current;

    // Skip comparison on first load
    if (previousItems.length === 0) {
      prevDataRef.current = currentItems;
      return;
    }

    // Create map for easier lookup
    const prevMap = new Map(previousItems.map(item => [item.item, item]));

    const changes = new Map<string, RowChangeState>();
    const now = Date.now();

    // Check for new and updated items
    currentItems.forEach(currentItem => {
      const prevItem = prevMap.get(currentItem.item);

      if (!prevItem) {
        // New item added
        changes.set(currentItem.item, { type: 'added', timestamp: now });
      } else {
        // Check if any fields changed
        const hasChanged =
          prevItem.status !== currentItem.status ||
          prevItem.eta !== currentItem.eta ||
          prevItem.date_arrived !== currentItem.date_arrived ||
          prevItem.purchase_order_id !== currentItem.purchase_order_id ||
          prevItem.updated_at !== currentItem.updated_at;

        if (hasChanged) {
          changes.set(currentItem.item, { type: 'updated', timestamp: now });
        }
      }
    });

    // Check for deleted items and save their full data
    const deletedItemsWithData = previousItems.filter(
      prev => !currentItems.some(curr => curr.item === prev.item)
    );

    deletedItemsWithData.forEach(deletedItem => {
      // Item was deleted
      changes.set(deletedItem.item, { type: 'deleted', timestamp: now });
    });

    // Update previous data reference
    prevDataRef.current = currentItems;

    // Set row changes and schedule cleanup
    if (changes.size > 0) {
      setRowChanges(changes);

      // Handle deleted items
      if (deletedItemsWithData.length > 0) {
        const deletedKeys = deletedItemsWithData.map(item => item.item);

        // Add to deletingRows to keep them visible during animation
        setDeletingRows(new Set(deletedKeys));

        // Keep the row visible with highlight for 3 seconds, then remove
        // This gives time for both the red highlight and the exit animation
        const deleteTimer = setTimeout(() => {
          setDeletingRows(new Set());
          setRowChanges(prev => {
            const updated = new Map(prev);
            deletedKeys.forEach(key => updated.delete(key));
            return updated;
          });
        }, 3000);

        return () => {
          clearTimeout(deleteTimer);
        };
      }

      // Clear highlights after 1 second for added/updated
      const timer = setTimeout(() => {
        setRowChanges(new Map());
      }, 1000);

      return () => clearTimeout(timer);
    }

    return undefined;
  }, [data?.procurement_items, isLoading]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
          <p className="text-muted-foreground text-sm">Loading table data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-md space-y-4 text-center">
          <AlertCircle className="text-destructive mx-auto h-12 w-12" />
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Error Loading Data</h3>
            <p className="text-muted-foreground text-sm">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <p className="text-muted-foreground text-sm">No data available</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex-1 overflow-auto p-6">
        <div className="space-y-8">
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold">Procurement Items</h3>
              <p className="text-muted-foreground text-sm">
                Current status of all procurement items
              </p>
            </div>

            {data.procurement_items.length === 0 ? (
              <div className="bg-muted/50 rounded-lg border p-8 text-center">
                <p className="text-muted-foreground text-sm">
                  No procurement items found
                </p>
              </div>
            ) : (
              <div className="rounded-lg border">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-muted/50">
                      {table.getHeaderGroups().map(headerGroup => (
                        <tr key={headerGroup.id}>
                          {headerGroup.headers.map(header => (
                            <th
                              key={header.id}
                              className="border-b px-4 py-3 text-left text-xs font-medium tracking-wide uppercase"
                            >
                              {header.isPlaceholder
                                ? null
                                : flexRender(
                                    header.column.columnDef.header,
                                    header.getContext()
                                  )}
                            </th>
                          ))}
                        </tr>
                      ))}
                    </thead>
                    <tbody>
                      <AnimatePresence mode="popLayout">
                        {table.getRowModel().rows.map(row => {
                          const item = row.original;
                          const change = rowChanges.get(item.item);

                          return (
                            <motion.tr
                              key={item.item}
                              layout
                              initial={
                                change?.type === 'added'
                                  ? { opacity: 0, x: -20 }
                                  : false
                              }
                              animate={{
                                opacity: 1,
                                x: 0,
                              }}
                              exit={{
                                opacity: 0,
                                x: -50,
                                transition: { duration: 0.5 },
                              }}
                              transition={{
                                layout: { duration: 0.3 },
                                opacity: { duration: 0.3 },
                              }}
                              className={cn(
                                'border-b transition-colors duration-1000 last:border-0',
                                !change && 'hover:bg-muted/30',
                                change?.type === 'deleted' &&
                                  'bg-red-100/80 dark:bg-red-900/40',
                                change?.type === 'added' &&
                                  'bg-green-100/80 dark:bg-green-900/30',
                                change?.type === 'updated' &&
                                  'bg-blue-100/80 dark:bg-blue-900/30'
                              )}
                            >
                              {row.getVisibleCells().map(cell => (
                                <td key={cell.id} className="px-4 py-3 text-sm">
                                  {flexRender(
                                    cell.column.columnDef.cell,
                                    cell.getContext()
                                  )}
                                </td>
                              ))}
                            </motion.tr>
                          );
                        })}
                      </AnimatePresence>
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          {data.schedule && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold">Project Schedule</h3>
                <p className="text-muted-foreground text-sm">
                  Master construction schedule information
                </p>
              </div>
              <div className="bg-muted/50 rounded-lg border p-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-muted-foreground text-xs font-medium uppercase">
                      Project Name
                    </p>
                    <p className="mt-1 text-sm font-semibold">
                      {data.schedule.project_name}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs font-medium uppercase">
                      Workflow ID
                    </p>
                    <p className="mt-1 font-mono text-xs">
                      {data.schedule.workflow_id}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs font-medium uppercase">
                      Start Date
                    </p>
                    <p className="mt-1 text-sm">
                      {new Date(
                        data.schedule.project_start_date
                      ).toLocaleDateString()}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs font-medium uppercase">
                      End Date
                    </p>
                    <p className="mt-1 text-sm">
                      {new Date(
                        data.schedule.project_end_date
                      ).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-muted-foreground text-xs font-medium uppercase">
                      Last Updated
                    </p>
                    <p className="mt-1 text-sm">
                      {new Date(data.schedule.updated_at).toLocaleString()}
                    </p>
                  </div>
                </div>

                {scheduleData?.deliveries && (
                  <div className="mt-4 space-y-2">
                    <p className="text-muted-foreground text-xs font-medium uppercase">
                      Deliveries
                    </p>
                    <div className="space-y-2">
                      {scheduleData.deliveries.map(
                        (
                          delivery: {
                            item: string;
                            required_by: string;
                            buffer_days: number;
                          },
                          idx: number
                        ) => (
                          <div
                            key={idx}
                            className="bg-background flex items-center justify-between rounded border p-2 text-sm"
                          >
                            <span className="font-medium">{delivery.item}</span>
                            <div className="flex gap-4 text-xs">
                              <span className="text-muted-foreground">
                                Required: {delivery.required_by}
                              </span>
                              <span className="text-muted-foreground">
                                Buffer: {delivery.buffer_days}d
                              </span>
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
