import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  FileText,
  LayoutDashboard,
  PlayCircle,
  ClipboardList,
} from "lucide-react";

export type AppPage = "cases" | "launch" | "progress" | "reports";

interface SidebarProps {
  active: AppPage;
  onNavigate: (page: AppPage) => void;
}

const NAV_ITEMS: Array<{ id: AppPage; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { id: "cases", label: "Cases", icon: ClipboardList },
  { id: "launch", label: "Launch", icon: PlayCircle },
  { id: "progress", label: "Progress", icon: FileText },
  { id: "reports", label: "Reports", icon: LayoutDashboard },
];

export function Sidebar({ active, onNavigate }: SidebarProps) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/40">
      <div className="flex h-12 items-center gap-2 px-4">
        <span className="text-sm font-bold tracking-tight">ckl-bench</span>
        <Badge variant="muted" className="text-[10px] uppercase">app</Badge>
      </div>
      <Separator />
      <nav className="flex-1 space-y-1 p-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active === item.id
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
