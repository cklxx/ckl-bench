import type { BenchData } from "./types";

declare global {
  interface Window {
    __CKL_BENCH_DATA__?: BenchData;
  }
}

/** Read the injected data from the Python side. Falls back to a stub in dev. */
export function readData(): BenchData {
  const data = window.__CKL_BENCH_DATA__;
  if (data) return data;

  // Dev fallback: no data injected — show an empty report page.
  if (import.meta.env.DEV) {
    return { page: "report" };
  }
  return { page: "report" };
}

export function hasData(data: BenchData): boolean {
  switch (data.page) {
    case "report":
      return !!data.summary;
    case "dashboard":
      return !!data.runs && data.runs.length > 0;
    case "probe":
      return !!data.probe_rows && data.probe_rows.length > 0;
    case "diff":
      return !!data.diff;
    case "app":
      // App mode fetches from the API; always considered "ready".
      return true;
    default:
      return false;
  }
}
