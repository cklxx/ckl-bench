import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number): string {
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
