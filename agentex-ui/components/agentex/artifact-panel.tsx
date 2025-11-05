'use client';

import { useState, useEffect } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { X, ExternalLink, AlertCircle, Loader2 } from 'lucide-react';

import { ResizableSidebar } from '@/components/agentex/resizable-sidebar';
import { Button } from '@/components/ui/button';
import { useArtifactPanel } from '@/contexts/artifact-panel-context';

export function ArtifactPanel() {
  const { isOpen, url, eventTitle, closeArtifact } = useArtifactPanel();
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [isResizing, setIsResizing] = useState(false);

  // Reset loading/error states when URL changes
  useEffect(() => {
    setIsLoading(true);
    setHasError(false);
  }, [url]);

  const handleIframeLoad = () => {
    setIsLoading(false);
    setHasError(false);
  };

  const handleIframeError = () => {
    setIsLoading(false);
    setHasError(true);
  };

  const openInNewTab = () => {
    window.open(url ?? '', '_blank', 'noopener,noreferrer');
  };

  return (
    <AnimatePresence>
      {isOpen && url && (
        <motion.div
          key="traces-sidebar"
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
            {/* Resize overlay to prevent iframe from capturing mouse events */}
            {isResizing && (
              <div className="absolute inset-0 z-40 bg-transparent" />
            )}

            {/* Header */}
            <div className="flex items-center justify-between border-b border-orange-300 bg-gradient-to-r from-orange-50 to-yellow-50 px-4 py-3 dark:border-orange-700 dark:from-orange-950 dark:to-yellow-950">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <ExternalLink className="h-4 w-4 flex-shrink-0 text-orange-600 dark:text-orange-400" />
                <h2
                  className="truncate text-sm font-medium text-orange-900 dark:text-orange-100"
                  title={eventTitle || ''}
                >
                  {eventTitle || 'External Content'}
                </h2>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={openInNewTab}
                  className="text-xs"
                >
                  <ExternalLink className="mr-1 h-3 w-3" />
                  Open in Tab
                </Button>
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

            {/* Content */}
            <div className="bg-muted/10 relative flex-1">
              {isLoading && (
                <div className="bg-background absolute inset-0 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
                    <p className="text-muted-foreground text-sm">
                      Loading content...
                    </p>
                  </div>
                </div>
              )}

              {hasError && (
                <div className="bg-background absolute inset-0 flex items-center justify-center p-8">
                  <div className="max-w-md space-y-4 text-center">
                    <AlertCircle className="text-destructive mx-auto h-12 w-12" />
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold">
                        Cannot Display Content
                      </h3>
                      <p className="text-muted-foreground text-sm">
                        This website cannot be embedded due to security
                        restrictions. Many sites block iframe embedding to
                        protect user security.
                      </p>
                    </div>
                    <Button onClick={openInNewTab} className="mt-4">
                      <ExternalLink className="mr-2 h-4 w-4" />
                      Open in New Tab
                    </Button>
                    <div className="border-border mt-4 border-t pt-4">
                      <p className="text-muted-foreground text-xs break-all">
                        {url}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <iframe
                src={url}
                className="h-full w-full border-0"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
                allow="payment"
                onLoad={handleIframeLoad}
                onError={handleIframeError}
                title={eventTitle || 'External content'}
              />
            </div>
          </ResizableSidebar>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
