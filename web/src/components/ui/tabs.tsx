import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Minimal, accessible tabs via context. No external deps.
 * Usage:
 *   <Tabs value={tab} onValueChange={setTab}>
 *     <TabsList>
 *       <TabsTrigger value="overview">Overview</TabsTrigger>
 *       <TabsTrigger value="heatmap">Heatmap</TabsTrigger>
 *     </TabsList>
 *     <TabsContent value="overview">...</TabsContent>
 *     <TabsContent value="heatmap">...</TabsContent>
 *   </Tabs>
 */
interface TabsContextValue {
  value: string;
  onValueChange: (value: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabs(): TabsContextValue {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error("Tabs.* must be used within <Tabs>");
  return ctx;
}

interface TabsProps {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

export function Tabs({ value, onValueChange, children, className }: TabsProps) {
  return (
    <TabsContext.Provider value={{ value, onValueChange }}>
      <div className={cn("space-y-4", className)}>{children}</div>
    </TabsContext.Provider>
  );
}

interface TabsListProps {
  children: React.ReactNode;
  className?: string;
}

export function TabsList({ children, className }: TabsListProps) {
  return (
    <div
      className={cn(
        "inline-flex h-9 items-center gap-1 rounded-lg bg-muted/60 p-1",
        className
      )}
      role="tablist"
    >
      {children}
    </div>
  );
}

interface TabsTriggerProps {
  value: string;
  children: React.ReactNode;
  className?: string;
}

export function TabsTrigger({ value, children, className }: TabsTriggerProps) {
  const { value: active, onValueChange } = useTabs();
  const isActive = value === active;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      onClick={() => onValueChange(value)}
      className={cn(
        "inline-flex h-7 items-center rounded-md px-3 text-xs font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        isActive
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

interface TabsContentProps {
  value: string;
  children: React.ReactNode;
  className?: string;
}

export function TabsContent({ value, children, className }: TabsContentProps) {
  const { value: active } = useTabs();
  if (active !== value) return null;
  return (
    <div role="tabpanel" className={cn("animate-in fade-in duration-200", className)}>
      {children}
    </div>
  );
}
