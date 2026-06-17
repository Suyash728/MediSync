import { cn } from "@/lib/utils";

/**
 * Animated grey placeholder shown while content is loading.
 * Use Skeleton on every async view — never show a blank or spinner-only state.
 */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };
