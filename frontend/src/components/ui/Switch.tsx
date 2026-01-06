"use client";

import { forwardRef, InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {}

const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, ...props }, ref) => {
    return (
      <label className="relative inline-flex items-center cursor-pointer">
        <input
          type="checkbox"
          ref={ref}
          className="sr-only peer"
          {...props}
        />
        <div
          className={cn(
            "w-9 h-5 bg-muted rounded-full peer",
            "peer-checked:bg-primary",
            "after:content-[''] after:absolute after:top-0.5 after:left-0.5",
            "after:bg-white after:rounded-full after:h-4 after:w-4",
            "after:transition-transform after:duration-200",
            "peer-checked:after:translate-x-4",
            "peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2",
            className
          )}
        />
      </label>
    );
  }
);
Switch.displayName = "Switch";

export { Switch };

