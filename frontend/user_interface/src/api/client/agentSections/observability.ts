import { fetchApi, request } from "../core";

type BudgetResponse = {
  daily_limit_usd: number;
  alert_threshold_fraction: number;
  today_cost_usd: number;
  today_llm_cost_usd: number;
  today_cu_cost_usd: number;
};

type CostSummaryResponse = {
  tenant_id: string;
  days: number;
  daily_costs: Array<{
    tenant_id: string;
    date_key: string;
    total_cost_usd: number;
    llm_cost_usd: number;
    cu_cost_usd: number;
  }>;
};

function getBudget() {
  return request<BudgetResponse>("/api/observability/budget");
}

async function setBudget(dailyLimitUsd: number, alertThresholdFraction: number = 0.8): Promise<BudgetResponse> {
  const response = await fetchApi("/api/observability/budget", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      daily_limit_usd: dailyLimitUsd,
      alert_threshold_fraction: alertThresholdFraction,
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to save budget: ${response.status}`);
  }
  return response.json() as Promise<BudgetResponse>;
}

function getCostSummary(days: number = 7) {
  return request<CostSummaryResponse>(`/api/observability/cost?days=${days}`);
}

export { getBudget, getCostSummary, setBudget };
export type { BudgetResponse, CostSummaryResponse };
