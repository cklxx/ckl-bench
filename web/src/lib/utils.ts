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

export function scoreVariant(
  score: number
): "success" | "warning" | "destructive" {
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "destructive";
}

/**
 * Determine whether two 95% confidence intervals differ significantly.
 * Returns null when either CI is missing (can't determine), true when the
 * CIs don't overlap (significant at p < 0.05), false when they overlap.
 */
export function isSignificant(
  ciA: [number, number] | undefined,
  ciB: [number, number] | undefined
): boolean | null {
  if (!ciA || !ciB) return null;
  return ciA[1] < ciB[0] || ciB[1] < ciA[0];
}

/** Score achieved per dollar spent. Returns "—" when cost is missing or zero. */
export function formatScorePerDollar(
  score: number | undefined | null,
  cost: number | undefined | null
): string {
  if (score == null || cost == null || cost <= 0) return "—";
  return (score / cost).toFixed(2);
}

/** Score achieved per 1M tokens. Returns "—" when tokens are missing or zero. */
export function formatScorePerMTokens(
  score: number | undefined | null,
  tokens: number | undefined | null
): string {
  if (score == null || tokens == null || tokens <= 0) return "—";
  return (score / (tokens / 1_000_000)).toFixed(2);
}

/** Badge variant for a difficulty level (medium < hard < extreme < frontier). */
export function difficultyVariant(
  d: string | null | undefined
): "destructive" | "warning" | "success" | "outline" {
  if (d === "extreme") return "destructive";
  if (d === "hard") return "destructive";
  if (d === "medium") return "warning";
  if (d === "frontier") return "outline";
  return "outline";
}
