import { Skeleton } from "@/components/ui/skeleton";

export function Loading() {
  return (
    <div className="flex flex-col gap-8">
      <Skeleton className="w-full h-50 animate-pulse" />
      <Skeleton className="w-3/4 h-25 animate-pulse" />
    </div>
  );
}
