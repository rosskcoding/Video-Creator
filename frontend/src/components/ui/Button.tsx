import { forwardRef, ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "secondary" | "outline" | "ghost" | "destructive";
  size?: "default" | "sm" | "lg" | "icon";
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 font-medium transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:pointer-events-none disabled:opacity-50",
          // Variants
          variant === "default" && "bg-primary text-primary-foreground hover:bg-primary/90",
          variant === "secondary" && "bg-secondary text-secondary-foreground hover:bg-secondary/80",
          variant === "outline" && "border border-border bg-transparent hover:bg-muted",
          variant === "ghost" && "hover:bg-muted",
          variant === "destructive" && "bg-destructive text-destructive-foreground hover:bg-destructive/90",
          // Sizes
          size === "default" && "h-9 px-4 text-[13px] rounded-sm",
          size === "sm" && "h-8 px-3 text-[12px] rounded-sm",
          size === "lg" && "h-11 px-6 text-[14px] rounded-sm",
          size === "icon" && "h-9 w-9 rounded-sm",
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };

