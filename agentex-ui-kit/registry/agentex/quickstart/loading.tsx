import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <>
      <header className="w-full md:sticky mt-4 md:top-0 md:z-10 bg-background">
        <div className="mx-auto max-w-[min(100%-var(--spacing)*4,var(--spacing)*256)]">
          <h1>Loading...</h1>
        </div>
      </header>
      <main className="w-full">
        <Skeleton className="mx-auto w-[min(100%-var(--spacing)*4,var(--spacing)*256)] h-96 animate-pulse" />
      </main>
    </>
  );
}
