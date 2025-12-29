'use client';

import { useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { Brain, Eye, Loader2, RefreshCw } from 'lucide-react';

import { MemoryStrategyItem } from '@/components/memory-sidebar/memory-strategy-item';
import { Button } from '@/components/ui/button';
import { ResizableSidebar } from '@/components/ui/resizable-sidebar';
import { TooltipProvider } from '@/components/ui/tooltip';
import {
  useDeleteStrategy,
  useExtractStrategies,
  useMemory,
  useMemoryPreview,
} from '@/hooks/use-memory';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';

const MIN_SIDEBAR_WIDTH = 350;
const DEFAULT_SIDEBAR_WIDTH = 380;

type MemorySidebarProps = {
  isOpen: boolean;
};

export function MemorySidebar({ isOpen }: MemorySidebarProps) {
  const { agentName } = useSafeSearchParams();
  const [showPreview, setShowPreview] = useState(false);

  const {
    agentStrategies,
    userStrategies,
    isLoading,
    error,
  } = useMemory(agentName, 'default');

  const {
    preview,
    isLoading: previewLoading,
  } = useMemoryPreview(agentName, 'default');

  const deleteStrategy = useDeleteStrategy();
  const extractStrategies = useExtractStrategies();

  const totalStrategies = agentStrategies.length + userStrategies.length;

  const handleDelete = (strategyId: string) => {
    if (agentName) {
      deleteStrategy.mutate({ strategyId, agentId: agentName });
    }
  };

  const handleExtract = () => {
    if (agentName) {
      extractStrategies.mutate({ agentId: agentName, hours: 24 });
    }
  };

  return (
    <AnimatePresence>
      {agentName && (
        <motion.div
          key="memory-sidebar"
          initial={{ opacity: 0, x: 20, width: 0 }}
          animate={{ opacity: 1, x: 0, width: 'auto' }}
          exit={{ opacity: 0, x: 20, width: 0 }}
          transition={{ duration: 0.25, ease: 'easeInOut' }}
        >
          <ResizableSidebar
            side="right"
            storageKey="memorySidebarWidth"
            defaultWidth={DEFAULT_SIDEBAR_WIDTH}
            minWidth={MIN_SIDEBAR_WIDTH}
            isCollapsed={!isOpen}
            collapsedWidth={0}
          >
            <TooltipProvider>
              <div className="flex h-full flex-col">
                {/* Header */}
                <div className="border-border border-b px-4 py-4">
                  <div className="flex items-center gap-2">
                    <Brain className="text-foreground h-5 w-5" />
                    <h2 className="text-foreground text-lg font-semibold">
                      Agent Memory
                    </h2>
                  </div>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {totalStrategies} learned strategies
                  </p>
                </div>

                {/* Content */}
                <div className="flex-1 space-y-4 overflow-y-auto p-4">
                  {isLoading && (
                    <div className="text-muted-foreground flex items-center gap-2 text-sm">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading memory...
                    </div>
                  )}

                  {error && (
                    <div className="text-destructive text-sm">
                      Error: {error}
                    </div>
                  )}

                  {!isLoading && !error && totalStrategies === 0 && (
                    <div className="text-muted-foreground text-sm">
                      No strategies learned yet. Run extract to analyze traces.
                    </div>
                  )}

                  {/* Preview Mode */}
                  {showPreview && preview && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-foreground text-sm font-medium">
                          Prompt Preview
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setShowPreview(false)}
                        >
                          Back to list
                        </Button>
                      </div>
                      <pre className="bg-muted text-foreground max-h-96 overflow-auto rounded-lg p-3 text-xs whitespace-pre-wrap">
                        {preview.content}
                      </pre>
                    </div>
                  )}

                  {/* Strategy Lists */}
                  {!showPreview && (
                    <>
                      {/* Agent-level strategies */}
                      {agentStrategies.length > 0 && (
                        <div className="space-y-2">
                          <h3 className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
                            Agent Memory ({agentStrategies.length})
                          </h3>
                          <div className="space-y-2">
                            {agentStrategies.map(strategy => (
                              <MemoryStrategyItem
                                key={strategy.id}
                                strategy={strategy}
                                onDelete={handleDelete}
                              />
                            ))}
                          </div>
                        </div>
                      )}

                      {/* User-level strategies */}
                      {userStrategies.length > 0 && (
                        <div className="space-y-2">
                          <h3 className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
                            User Memory ({userStrategies.length})
                          </h3>
                          <div className="space-y-2">
                            {userStrategies.map(strategy => (
                              <MemoryStrategyItem
                                key={strategy.id}
                                strategy={strategy}
                                onDelete={handleDelete}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Actions */}
                <div className="border-border space-y-2 border-t p-4">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={handleExtract}
                    disabled={extractStrategies.isPending}
                  >
                    {extractStrategies.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCw className="mr-2 h-4 w-4" />
                    )}
                    Extract from Recent Traces
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full"
                    onClick={() => setShowPreview(!showPreview)}
                    disabled={previewLoading || totalStrategies === 0}
                  >
                    <Eye className="mr-2 h-4 w-4" />
                    {showPreview ? 'Hide Preview' : 'Preview Prompt'}
                  </Button>
                </div>
              </div>
            </TooltipProvider>
          </ResizableSidebar>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
