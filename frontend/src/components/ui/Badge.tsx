import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "success" | "warning" | "error" | "outline";
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border",
        variant === "default" && "bg-primary/10 text-primary border-primary/20",
        variant === "secondary" && "bg-muted text-muted-foreground border-transparent",
        variant === "success" && "bg-emerald-50 text-emerald-700 border-emerald-200",
        variant === "warning" && "bg-amber-50 text-amber-700 border-amber-200",
        variant === "error" && "bg-red-50 text-red-700 border-red-200",
        variant === "outline" && "bg-transparent border-border text-muted-foreground",
        className
      )}
      {...props}
    />
  );
}

export { Badge };

