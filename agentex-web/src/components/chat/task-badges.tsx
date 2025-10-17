'use client';

import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Switch} from '@/components/ui/switch';
import type {Task} from 'agentex/resources';
import {ActivitySquare, Copy, Hash} from 'lucide-react';
import Link from 'next/link';

interface TaskBadgesProps {
  isCopied: boolean;
  task: Task;
  copyTaskId: () => void;
  autoScrollEnabled: boolean;
  setAutoScrollEnabled: (enabled: boolean) => void;
}

const getStatusColor = (status: Task['status']) => {
  switch (status) {
    case 'RUNNING':
      return 'bg-blue-100 text-blue-800 border-blue-300';
    case 'COMPLETED':
      return 'bg-green-100 text-green-800 border-green-300';
    case 'FAILED':
      return 'bg-red-100 text-red-800 border-red-300';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-300';
  }
};

const TaskBadges: React.FC<TaskBadgesProps> = ({
  isCopied,
  task,
  copyTaskId,
  autoScrollEnabled,
  setAutoScrollEnabled,
}) => {
  return (
    <div className="mx-auto max-w-5xl px-4">
      <div className="flex flex-wrap items-center justify-between gap-2 p-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Task ID */}
          <Badge variant="secondary" className="flex items-center space-x-1 pr-1 text-sm">
            <Hash className="h-4 w-4" />
            <span className="font-mono">Task ID: {task?.id.substring(0, 8)}</span>
            <Button
              variant="ghost"
              size="icon"
              className={`ml-1 h-6 w-6 transition-colors ${
                isCopied
                  ? 'bg-green-100 text-green-800 hover:bg-green-200 hover:text-green-900'
                  : 'hover:bg-gray-200 hover:text-gray-900'
              }`}
              onClick={copyTaskId}
            >
              <Copy className="h-3 w-3" />
              <span className="sr-only">Copy Task ID</span>
            </Button>
          </Badge>

          {/* View Traces Button */}
          <Link href={`/tasks/${task.id}/traces`}>
            <Button variant="outline" size="sm" className="flex h-7 items-center gap-1">
              <ActivitySquare className="h-3.5 w-3.5" />
              Investigate Traces
            </Button>
          </Link>
        </div>

        {/* Right side with autoscroll and status */}
        <div className="flex items-center gap-3">
          {/* Autoscroll toggle */}
          <div className="flex items-center gap-2">
            <label htmlFor="autoscroll-toggle-input" className="text-sm text-gray-500">
              Auto-scroll
            </label>
            <Switch
              id="autoscroll-toggle-input"
              checked={autoScrollEnabled}
              onCheckedChange={setAutoScrollEnabled}
            />
          </div>

          {/* Status badge */}
          <Badge
            variant="outline"
            className={`flex items-center gap-1 border text-sm ${getStatusColor(task.status)}`}
          >
            {task.status}
          </Badge>
        </div>
      </div>
    </div>
  );
};

export default TaskBadges;
