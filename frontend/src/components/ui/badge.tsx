import type { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const pillBadgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap tabular-nums",
  {
    variants: {
      variant: {
        default:
          "border-indigo-500/30 bg-indigo-500/12 text-indigo-700 dark:text-indigo-300",
        secondary:
          "border-border bg-secondary/80 text-secondary-foreground",
        outline: "border-border bg-transparent text-muted-foreground",
        success:
          "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
        warning:
          "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
        destructive:
          "border-rose-500/30 bg-rose-500/12 text-rose-700 dark:text-rose-300",
        info:
          "border-cyan-500/30 bg-cyan-500/12 text-cyan-700 dark:text-cyan-300",
        violet:
          "border-violet-500/30 bg-violet-500/12 text-violet-700 dark:text-violet-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof pillBadgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(pillBadgeVariants({ variant }), className)} {...props} />
  );
}
