"use client";

import { createContext, useContext, useState, ReactNode, HTMLAttributes } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

interface DialogProps {
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

function Dialog({ children, open: controlledOpen, onOpenChange }: DialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  
  const open = controlledOpen ?? uncontrolledOpen;
  const setOpen = onOpenChange ?? setUncontrolledOpen;

  return (
    <DialogContext.Provider value={{ open, setOpen }}>
      {children}
    </DialogContext.Provider>
  );
}

function DialogTrigger({ children, className, ...props }: HTMLAttributes<HTMLButtonElement>) {
  const context = useContext(DialogContext);
  if (!context) throw new Error("DialogTrigger must be used within Dialog");

  return (
    <button
      onClick={() => context.setOpen(true)}
      className={className}
      {...props}
    >
      {children}
    </button>
  );
}

function DialogContent({ children, className, ...props }: HTMLAttributes<HTMLDivElement>) {
  const context = useContext(DialogContext);
  if (!context) throw new Error("DialogContent must be used within Dialog");

  if (!context.open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 animate-fade-in"
        onClick={() => context.setOpen(false)}
      />
      
      {/* Content */}
      <div
        className={cn(
          "relative bg-surface rounded-lg border border-border shadow-dropdown",
          "w-full max-w-lg mx-4 animate-slide-up",
          className
        )}
        {...props}
      >
        <button
          type="button"
          onClick={() => context.setOpen(false)}
          className="absolute top-4 right-4 p-1 rounded-sm hover:bg-muted transition-colors"
          title="Close dialog"
          aria-label="Close dialog"
        >
          <X className="w-4 h-4 text-muted-foreground" />
        </button>
        {children}
      </div>
    </div>
  );
}

function DialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("p-6 pb-0", className)} {...props} />
  );
}

function DialogTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2 className={cn("text-page-title", className)} {...props} />
  );
}

function DialogDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("text-[13px] text-muted-foreground mt-1.5", className)} {...props} />
  );
}

function DialogFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex justify-end gap-2 p-6 pt-4", className)}
      {...props}
    />
  );
}

export { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter };

