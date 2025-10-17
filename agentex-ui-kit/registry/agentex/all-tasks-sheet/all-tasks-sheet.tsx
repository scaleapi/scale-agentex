import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { TaskStatusIcon } from "@/registry/agentex/task-status-icon/task-status-icon";
import type { Task } from "agentex/resources";
import { formatDistanceToNow } from "date-fns";
import { useEffect, useRef, useState } from "react";

export type AllTasksSheetProps = {
  tasks: Task[];
  /**
   * omitted: uncontrolled
   * null: controlled + no task selected
   * Task["id"]: controlled + task selected
   */
  selectedTaskID?: Task["id"] | null;
  onSelectTask?: (taskID: Task["id"] | null) => void;
};

/**
 * WIP
 */
export function AllTasksSheet({
  tasks,
  selectedTaskID: parentSelectedTaskID,
  onSelectTask,
}: AllTasksSheetProps) {
  const [open, setOpen] = useState(false);

  const isSelectedTaskIDParentControlled = parentSelectedTaskID !== undefined;
  const [controlledSelectedTaskID, setControlledSelectedTaskID] = useState<
    Task["id"] | null
  >(null);
  const selectedTaskID = isSelectedTaskIDParentControlled
    ? parentSelectedTaskID
    : controlledSelectedTaskID;

  const handleTaskSelect = (taskID: Task["id"] | null) => {
    setControlledSelectedTaskID(taskID);
    onSelectTask?.(taskID);
    setOpen(false);
  };

  const isSelectedTaskIDParentControlledRef = useRef(
    isSelectedTaskIDParentControlled
  );
  useEffect(() => {
    if (
      isSelectedTaskIDParentControlledRef.current !==
      isSelectedTaskIDParentControlled
    ) {
      console.error(
        "AllTasksSheet: selectedTaskID prop changed from controlled to uncontrolled or vice versa. This may lead to unexpected behavior."
      );
    }
  }, [isSelectedTaskIDParentControlled]);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline">
          View All Tasks
        </Button>
      </SheetTrigger>
      <SheetContent className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Tasks</SheetTitle>
          <SheetDescription className="hidden">
            List of all tasks
          </SheetDescription>
        </SheetHeader>
        <div className="w-full flex flex-col-reverse pb-8 items-stretch">
          {tasks.map((task, index) => (
            <Button
              variant={selectedTaskID === task.id ? "outline" : "ghost"}
              className="justify-start m-2 gap-2"
              key={index}
              onClick={() => handleTaskSelect(task.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  handleTaskSelect(task.id);
                }
              }}
            >
              <TaskStatusIcon status={task.status} />
              <span className="truncate">
                {task.name ??
                  "Unnamed task from " +
                    (task.created_at
                      ? formatDistanceToNow(task.created_at, {
                          addSuffix: true,
                          includeSeconds: false,
                        })
                      : "")}
              </span>
            </Button>
          ))}
          {tasks.length === 0 && (
            <p className="text-muted-foreground my-2 mx-auto">No tasks found.</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
