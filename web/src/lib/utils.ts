import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number | undefined | null, digits = 1): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | undefined | null): string {
  if (value == null) return "—";
  return value.toLocaleString("en-US");
}

export function formatCost(value: number): string {
  if (value === 0) return "$0.00";
  if (value < 0.001) return `$${value.toFixed(5)}`;
  return `$${value.toFixed(4)}`;
}

export function shortId(value: string, len = 16): string {
  return value.length > len ? value.slice(0, len) + "…" : value;
}
