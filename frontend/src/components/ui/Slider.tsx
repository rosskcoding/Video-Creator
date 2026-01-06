"use client";

import { forwardRef, InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface SliderProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  showValue?: boolean;
  unit?: string;
  minLabel?: string;
  maxLabel?: string;
}

const Slider = forwardRef<HTMLInputElement, SliderProps>(
  ({ className, showValue = true, unit = "", minLabel, maxLabel, ...props }, ref) => {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <input
            type="range"
            ref={ref}
            className={cn(
              "w-full h-2 bg-muted rounded-full appearance-none cursor-pointer",
              "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4",
              "[&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full",
              "[&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-pointer",
              "[&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:hover:scale-110",
              className
            )}
            {...props}
          />
          {showValue && (
            <span className="text-[13px] text-muted-foreground min-w-[3rem] text-right">
              {props.value}{unit}
            </span>
          )}
        </div>
        {(minLabel || maxLabel) && (
          <div className="flex justify-between text-[11px] text-muted-foreground px-0.5">
            <span>{minLabel}</span>
            <span>{maxLabel}</span>
          </div>
        )}
      </div>
    );
  }
);
Slider.displayName = "Slider";

export { Slider };

