'use client';

import { useState } from 'react';

import dynamic from 'next/dynamic';

import { useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { X, ExternalLink } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { ResizableSidebar } from '@/components/ui/resizable-sidebar';
import { useArtifactPanel } from '@/contexts/artifact-panel-context';
import { useTaskData, taskDataKeys } from '@/hooks/use-task-data';

const PDFViewer = dynamic(
  () => import('@/components/artifacts/pdf-viewer').then(mod => mod.PDFViewer),
  {
    ssr: false,
  }
);

const MapViewer = dynamic(
  () => import('@/components/artifacts/map-viewer').then(mod => mod.MapViewer),
  {
    ssr: false,
  }
);

const DataTableViewer = dynamic(
  () =>
    import('@/components/artifacts/data-table-viewer').then(
      mod => mod.DataTableViewer
    ),
  {
    ssr: false,
  }
);

export function ArtifactPanel() {
  const {
    isOpen,
    pdfUrl,
    eventTitle,
    mapAddress,
    mapMetadata,
    taskId,
    closeArtifact,
  } = useArtifactPanel();
  const [isResizing, setIsResizing] = useState(false);
  const queryClient = useQueryClient();

  const {
    data: tableData,
    isLoading: isLoadingTables,
    error: tableError,
  } = useTaskData(taskId);

  const isPDF = !!pdfUrl;
  const isMap = !!mapAddress;
  const isDataTable = !!taskId;

  const openInNewTab = () => {
    window.open(pdfUrl ?? '', '_blank', 'noopener,noreferrer');
  };

  return (
    <AnimatePresence>
      {isOpen && (pdfUrl || mapAddress || taskId) && (
        <motion.div
          key="artifact-sidebar"
          initial={{ opacity: 0, x: 20, width: 0 }}
          animate={{ opacity: 1, x: 0, width: 'auto' }}
          exit={{ opacity: 0, x: 20, width: 0 }}
          transition={{ duration: 0.25, ease: 'easeInOut' }}
          layout
        >
          <ResizableSidebar
            side="right"
            storageKey="artifactPanelWidth"
            defaultWidth={800}
            minWidth={300}
            maxWidth={1200}
            collapsedWidth={0}
            isCollapsed={!isOpen}
            onResizingChange={setIsResizing}
          >
            <div className="flex h-full flex-col overflow-hidden">
              {/* Resize overlay to prevent PDF from capturing mouse events */}
              {isResizing && (
                <div className="absolute inset-0 z-50 bg-transparent" />
              )}

              <div className="flex items-center justify-between border-b px-4 py-3">
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <h2
                    className="text-muted-foreground truncate text-sm font-medium"
                    title={eventTitle || ''}
                  >
                    {eventTitle || 'Document Viewer'}
                  </h2>
                </div>
                <div className="flex items-center gap-2">
                  {pdfUrl && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={openInNewTab}
                      className="text-xs"
                    >
                      <ExternalLink className="mr-1 h-3 w-3" />
                      Open in Tab
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={closeArtifact}
                    className="h-8 w-8"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="bg-muted/10 relative flex-1 overflow-auto">
                {isDataTable ? (
                  <DataTableViewer
                    data={tableData ?? null}
                    isLoading={isLoadingTables}
                    error={tableError?.message ?? null}
                    onRefresh={() => {
                      queryClient.invalidateQueries({
                        queryKey: taskDataKeys.byTaskId(taskId),
                      });
                    }}
                  />
                ) : isMap ? (
                  <MapViewer address={mapAddress} metadata={mapMetadata} />
                ) : isPDF ? (
                  <PDFViewer url={pdfUrl} />
                ) : null}
              </div>
            </div>
          </ResizableSidebar>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
