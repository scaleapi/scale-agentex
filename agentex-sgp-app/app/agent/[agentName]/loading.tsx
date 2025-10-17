import { Skeleton } from '@/components/ui/skeleton';

export default function Loading() {
  return (
    <div className="flex fixed inset-0">
      {/* Sidebar Skeleton */}
      <div className="w-64 bg-sidebar border-r border-sidebar-border h-full flex flex-col">
        {/* Header Section */}
        <div className="pt-4 pb-6 pr-4 pl-2 border-b border-sidebar-border">
          <div className="flex items-center gap-2 pl-2 pb-4">
            <Skeleton className="h-6 w-24" />
          </div>
          <Skeleton className="h-10 w-full" />
        </div>

        {/* Task List */}
        <div className="flex flex-col overflow-y-auto py-4 pl-4 pr-2 gap-5">
          {[...Array(8)].map((_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      </div>

      {/* Main Content Area Skeleton */}
      <div className="flex flex-1 flex-col h-full bg-task-background">
        {/* Top Bar */}
        <div className="border-b border-border px-4 py-3">
          <Skeleton className="h-8 w-48" />
        </div>

        {/* Messages Area */}
        <div className="flex flex-col flex-1 overflow-y-auto items-center px-4 pt-4">
          <div className="flex flex-col gap-4 max-w-[800px] w-full">
            {/* User Message Skeleton */}
            <div className="flex justify-end">
              <Skeleton className="h-15 w-1/4 rounded-lg" />
            </div>

            {/* Agent Message Skeleton */}
            <div className="flex flex-col gap-3 justify-start">
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-7/8" />
              <Skeleton className="h-4 w-5/8 " />
            </div>

            {/* User Message Skeleton */}
            <div className="flex justify-end">
              <Skeleton className="h-15 w-1/4 rounded-lg" />
            </div>

            {/* Agent Message Skeleton */}
            <div className="flex flex-col gap-3 justify-start">
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-7/8" />
              <Skeleton className="h-4 w-5/8 " />
            </div>
          </div>
        </div>

        {/* Input Form Skeleton */}
        <div className="max-w-[800px] mx-auto w-full p-4 mb-2">
          <Skeleton className="w-full h-[100px] rounded-lg" />
        </div>
      </div>
    </div>
  );
}
