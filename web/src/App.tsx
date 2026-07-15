import { readData, hasData } from "@/lib/data";
import { ThemeToggle } from "@/components/theme-toggle";
import { ReportPage } from "@/pages/report-page";
import { DashboardPage } from "@/pages/dashboard-page";
import { ProbePage } from "@/pages/probe-page";
import { DiffPage } from "@/pages/diff-page";
import { BenchPage } from "@/pages/bench-page";
import { Badge } from "@/components/ui/badge";

export default function App() {
  const data = readData();
  const ready = hasData(data);

  if (data.page === "app") {
    return <BenchPage />;
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-12 max-w-7xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold tracking-tight">ckl-bench</span>
            <Badge variant="muted" className="text-[10px] uppercase">
              {data.page}
            </Badge>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {ready ? (
          renderPage(data)
        ) : (
          <EmptyState page={data.page} />
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
        <p className="text-xs text-muted-foreground">
          ckl-bench &middot; generated evaluation report
        </p>
      </footer>
    </div>
  );
}

function renderPage(data: ReturnType<typeof readData>) {
  switch (data.page) {
    case "report":
      return <ReportPage summary={data.summary!} results={data.results} />;
    case "dashboard":
      return <DashboardPage runs={data.runs!} />;
    case "probe":
      return (
        <ProbePage summary={data.probe_summary} rows={data.probe_rows!} />
      );
    case "diff":
      return <DiffPage diff={data.diff!} />;
    default:
      return <EmptyState page={data.page} />;
  }
}

function EmptyState({ page }: { page: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <p className="text-lg font-medium">No data available</p>
      <p className="mt-1 text-sm text-muted-foreground">
        The {page} page has no data to display yet.
      </p>
    </div>
  );
}
