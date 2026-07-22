import type { BenchData } from "./types";

declare global {
  interface Window {
    __CKL_BENCH_DATA__?: BenchData;
  }
}

/** Read inert JSON bootstrap data, with legacy window assignment compatibility. */
export function readData(): BenchData {
  const element = document.getElementById("ckl-bench-data");
  if (element?.textContent) {
    try {
      return JSON.parse(element.textContent) as BenchData;
    } catch {
      // Fall through to the legacy carrier during backend migration.
    }
  }
  return window.__CKL_BENCH_DATA__ ?? { page: "report" };
}

export function readAppBootstrap(): import("./types").AppBootstrap | null {
  const data = readData();
  return data.page === "app" && typeof data.ws_port === "number" && typeof data.api_token === "string"
    ? { page: "app", ws_port: data.ws_port, api_token: data.api_token }
    : null;
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
