'use client';

import { useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight, Minus, Plus, Trash2 } from 'lucide-react';

import { IconButton } from '@/components/ui/icon-button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import type { StrategyItem } from '@/lib/memory-types';

type MemoryStrategyItemProps = {
  strategy: StrategyItem;
  onDelete?: (strategyId: string) => void;
};

export function MemoryStrategyItem({
  strategy,
  onDelete,
}: MemoryStrategyItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const isSuccess = strategy.source_outcome === 'success';
  const SourceIcon = isSuccess ? Plus : Minus;
  const sourceColor = isSuccess ? 'text-green-500' : 'text-red-500';

  return (
    <div className="border-border rounded-lg border">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="hover:bg-muted/50 flex w-full items-center gap-2 rounded-lg p-3 text-left transition-colors"
      >
        <motion.div
          animate={{ rotate: isExpanded ? 90 : 0 }}
          transition={{ duration: 0.15 }}
        >
          <ChevronRight className="text-muted-foreground h-4 w-4" />
        </motion.div>

        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <SourceIcon className={`h-4 w-4 flex-shrink-0 ${sourceColor}`} />
          </TooltipTrigger>
          <TooltipContent>
            Learned from {isSuccess ? 'success' : 'failure'}
          </TooltipContent>
        </Tooltip>

        <span className="text-foreground flex-1 truncate text-sm font-medium">
          {strategy.title}
        </span>

        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <span className="text-muted-foreground text-xs">
              {strategy.usage_count}×
            </span>
          </TooltipTrigger>
          <TooltipContent>Used {strategy.usage_count} times</TooltipContent>
        </Tooltip>
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-border space-y-3 border-t px-3 py-3">
              <p className="text-muted-foreground text-sm">
                {strategy.description}
              </p>

              <div className="space-y-1">
                <span className="text-foreground text-xs font-medium">
                  Principles:
                </span>
                <ul className="space-y-1">
                  {strategy.principles.map((principle, index) => (
                    <li
                      key={index}
                      className="text-muted-foreground flex items-start gap-2 text-xs"
                    >
                      <span className="mt-1 h-1 w-1 flex-shrink-0 rounded-full bg-current" />
                      {principle}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex items-center justify-between pt-2">
                <div className="flex items-center gap-2">
                  {strategy.domain && (
                    <span className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs">
                      {strategy.domain}
                    </span>
                  )}
                  <span className="text-muted-foreground text-xs">
                    {Math.round(strategy.confidence * 100)}% confidence
                  </span>
                </div>

                {onDelete && (
                  <IconButton
                    variant="ghost"
                    iconSize="sm"
                    onClick={e => {
                      e.stopPropagation();
                      onDelete(strategy.id);
                    }}
                    aria-label="Delete strategy"
                    icon={Trash2}
                    className="text-destructive hover:text-destructive h-6 w-6"
                  />
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
