import * as React from "react";
import { cn } from "@/lib/utils";
import { lockScroll, unlockScroll } from "@/lib/scroll-lock";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  side?: "left" | "right";
  width?: string; // e.g. "75%", "520px"
  zIndex?: number; // stacked sheets: higher = on top
  children: React.ReactNode;
}

/**
 * Side sheet with a smooth slide-in. The panel is the scroll container
 * (the body stays locked via the shared scroll-lock counter), so open sheets
 * never fight each other for scroll. Stack multiple by passing zIndex.
 */
export function Sheet({
  open,
  onClose,
  side = "right",
  width = "75%",
  zIndex = 50,
  children,
}: SheetProps) {
  // Lock body scroll while open; shared counter handles stacked sheets.
  React.useEffect(() => {
    if (!open) return;
    lockScroll();
    return () => unlockScroll();
  }, [open]);

  if (!open) return null;

  const isRight = side === "right";

  return (
    <div className="fixed inset-0" style={{ zIndex }}>
      {/* Backdrop — fades in; click to close the top sheet */}
      <div
        className="absolute inset-0 bg-black/40 animate-in fade-in duration-200"
        onClick={onClose}
      />
      {/* Panel — slides in from the chosen side; scrolls internally */}
      <div
        className={cn(
          "absolute top-0 bottom-0 flex flex-col bg-background shadow-xl",
          isRight ? "right-0" : "left-0",
          "animate-in duration-300 ease-out",
          isRight ? "slide-in-from-right" : "slide-in-from-left"
        )}
        style={{ width }}
      >
        {children}
      </div>
    </div>
  );
}
