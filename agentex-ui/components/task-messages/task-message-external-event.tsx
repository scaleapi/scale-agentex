'use client';

import { memo, useState } from 'react';

import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle2,
  XCircle,
  Truck,
  MapPin,
  FileCheck,
  ChevronRight,
  ChevronDown,
  FileText,
  Map,
} from 'lucide-react';

import { useArtifactPanel } from '@/contexts/artifact-panel-context';
import type { EventType, ProcurementEvent } from '@/lib/types';
import { cn } from '@/lib/utils';

type TaskMessageExternalEventProps = {
  event: ProcurementEvent;
  timestamp?: string;
};

const eventConfig: Record<
  EventType,
  {
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    colorClasses: {
      dot: string;
      border: string;
      bg: string;
      text: string;
      iconColor: string;
    };
  }
> = {
  Submittal_Approved: {
    label: 'Submittal Approved',
    icon: FileCheck,
    colorClasses: {
      dot: 'bg-green-500',
      border: 'border-green-300 dark:border-green-700',
      bg: 'bg-green-50 dark:bg-green-950/30',
      text: 'text-green-900 dark:text-green-100',
      iconColor: 'text-green-600 dark:text-green-400',
    },
  },
  Shipment_Departed_Factory: {
    label: 'Shipment Departed',
    icon: Truck,
    colorClasses: {
      dot: 'bg-blue-500',
      border: 'border-blue-300 dark:border-blue-700',
      bg: 'bg-blue-50 dark:bg-blue-950/30',
      text: 'text-blue-900 dark:text-blue-100',
      iconColor: 'text-blue-600 dark:text-blue-400',
    },
  },
  Shipment_Arrived_Site: {
    label: 'Shipment Arrived',
    icon: MapPin,
    colorClasses: {
      dot: 'bg-blue-500',
      border: 'border-blue-300 dark:border-blue-700',
      bg: 'bg-blue-50 dark:bg-blue-950/30',
      text: 'text-blue-900 dark:text-blue-100',
      iconColor: 'text-blue-600 dark:text-blue-400',
    },
  },
  Inspection_Passed: {
    label: 'Inspection Passed',
    icon: CheckCircle2,
    colorClasses: {
      dot: 'bg-green-500',
      border: 'border-green-300 dark:border-green-700',
      bg: 'bg-green-50 dark:bg-green-950/30',
      text: 'text-green-900 dark:text-green-100',
      iconColor: 'text-green-600 dark:text-green-400',
    },
  },
  Inspection_Failed: {
    label: 'Inspection Failed',
    icon: XCircle,
    colorClasses: {
      dot: 'bg-red-500',
      border: 'border-red-300 dark:border-red-700',
      bg: 'bg-red-50 dark:bg-red-950/30',
      text: 'text-red-900 dark:text-red-100',
      iconColor: 'text-red-600 dark:text-red-400',
    },
  },
};

function TaskMessageExternalEventImpl({
  event,
  timestamp,
}: TaskMessageExternalEventProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { openPdf, openMap, closeArtifact, isOpen, pdfUrl, mapAddress } =
    useArtifactPanel();

  const config = eventConfig[event.event_type];
  const Icon = config.icon;

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    try {
      const date = new Date(dateStr);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const handleDocumentClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (event.document_url) {
      if (isOpen && pdfUrl === event.document_url) {
        closeArtifact();
      } else {
        openPdf(
          event.document_url,
          event.document_name || `${event.event_type} - ${event.item}`
        );
      }
    }
  };

  const handleMapClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (event.location_address) {
      if (isOpen && mapAddress === event.location_address) {
        closeArtifact();
      } else {
        openMap(event.location_address, `Location: ${event.item}`, {
          item: event.item,
          deliveryDate: event.date_arrived,
          dateDeparted: event.date_departed,
          eta: event.eta,
          eventType: event.event_type,
        });
      }
    }
  };

  return (
    <div className="w-full px-4">
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setIsExpanded(!isExpanded);
          }
        }}
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        className="group w-full cursor-pointer text-left transition-all hover:scale-[1.005] active:scale-[0.995]"
      >
        <div
          className={cn(
            'flex items-center gap-3 rounded-lg border px-4 py-3 shadow-sm transition-all',
            config.colorClasses.border,
            config.colorClasses.bg,
            'hover:shadow-md'
          )}
        >
          <Icon
            className={cn(
              'h-5 w-5 flex-shrink-0',
              config.colorClasses.iconColor
            )}
          />
          <div className="flex min-w-0 flex-1 items-baseline gap-2">
            <span
              className={cn(
                'truncate text-sm font-semibold',
                config.colorClasses.text
              )}
            >
              {config.label}:
            </span>
            <span
              className={cn(
                'truncate text-sm font-medium',
                config.colorClasses.text
              )}
            >
              {event.item}
            </span>
          </div>
          {event.document_url && (
            <button
              onClick={handleDocumentClick}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/5',
                config.colorClasses.text
              )}
            >
              <FileText className="h-3.5 w-3.5" />
              <span>View Doc</span>
            </button>
          )}
          {event.location_address && (
            <button
              onClick={handleMapClick}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/5',
                config.colorClasses.text
              )}
            >
              <Map className="h-3.5 w-3.5" />
              <span>View Map</span>
            </button>
          )}
          <div className="flex-shrink-0">
            {isExpanded ? (
              <ChevronDown
                className={cn('h-4 w-4', config.colorClasses.iconColor)}
              />
            ) : (
              <ChevronRight
                className={cn('h-4 w-4', config.colorClasses.iconColor)}
              />
            )}
          </div>
        </div>
      </div>
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div
              className={cn(
                'mt-2 rounded-lg border px-4 py-3 text-sm',
                config.colorClasses.border,
                config.colorClasses.bg
              )}
            >
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span
                    className={cn(
                      'font-medium',
                      config.colorClasses.text,
                      'opacity-70'
                    )}
                  >
                    Item:
                  </span>
                  <span className={cn('font-medium', config.colorClasses.text)}>
                    {event.item}
                  </span>
                </div>

                <div className="flex justify-between">
                  <span
                    className={cn(
                      'font-medium',
                      config.colorClasses.text,
                      'opacity-70'
                    )}
                  >
                    Event:
                  </span>
                  <span className={cn('font-medium', config.colorClasses.text)}>
                    {config.label}
                  </span>
                </div>

                {event.eta && (
                  <div className="flex justify-between">
                    <span
                      className={cn(
                        'font-medium',
                        config.colorClasses.text,
                        'opacity-70'
                      )}
                    >
                      ETA:
                    </span>
                    <span
                      className={cn('font-medium', config.colorClasses.text)}
                    >
                      {formatDate(event.eta)}
                    </span>
                  </div>
                )}

                {event.date_arrived && (
                  <div className="flex justify-between">
                    <span
                      className={cn(
                        'font-medium',
                        config.colorClasses.text,
                        'opacity-70'
                      )}
                    >
                      Arrived:
                    </span>
                    <span
                      className={cn('font-medium', config.colorClasses.text)}
                    >
                      {formatDate(event.date_arrived)}
                    </span>
                  </div>
                )}

                {event.inspection_date && (
                  <div className="flex justify-between">
                    <span
                      className={cn(
                        'font-medium',
                        config.colorClasses.text,
                        'opacity-70'
                      )}
                    >
                      Inspection Date:
                    </span>
                    <span
                      className={cn('font-medium', config.colorClasses.text)}
                    >
                      {formatDate(event.inspection_date)}
                    </span>
                  </div>
                )}

                {timestamp && (
                  <div className="flex justify-between">
                    <span
                      className={cn(
                        'font-medium',
                        config.colorClasses.text,
                        'opacity-70'
                      )}
                    >
                      Received:
                    </span>
                    <span
                      className={cn('font-medium', config.colorClasses.text)}
                    >
                      {formatDate(timestamp)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const TaskMessageExternalEvent = memo(TaskMessageExternalEventImpl);

export { TaskMessageExternalEvent };
