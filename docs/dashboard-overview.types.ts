export const DASHBOARD_SCHEMA_VERSION = "2026-05-11.v1" as const;

export type UsageWindow = "24h" | "7d" | "30d" | "all";
export type SavingsWindow = "7d" | "30d";

export interface UsageSummary {
  window: UsageWindow;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  charged_credits: number;
  provider_cost: number;
}

export interface SavingsEstimate {
  window: SavingsWindow;
  baseline_strong_cost: number;
  actual_charged_credits: number;
  provider_cost: number;
  savings_vs_charged: number;
  savings_vs_provider: number;
  savings_ratio_vs_charged: number;
  savings_ratio_vs_provider: number;
}

export interface DashboardOverview {
  schema_version: typeof DASHBOARD_SCHEMA_VERSION;
  token: string;
  balance_credits: number;
  generated_at: string;
  usage_7d: UsageSummary;
  usage_30d: UsageSummary;
  savings_estimate_7d: SavingsEstimate;
  savings_estimate_30d: SavingsEstimate;
}

export function isDashboardOverview(input: unknown): input is DashboardOverview {
  if (!input || typeof input !== "object") {
    return false;
  }
  const obj = input as Record<string, unknown>;
  return (
    obj.schema_version === DASHBOARD_SCHEMA_VERSION &&
    typeof obj.token === "string" &&
    typeof obj.balance_credits === "number" &&
    typeof obj.generated_at === "string" &&
    typeof obj.usage_7d === "object" &&
    typeof obj.usage_30d === "object" &&
    typeof obj.savings_estimate_7d === "object" &&
    typeof obj.savings_estimate_30d === "object"
  );
}
