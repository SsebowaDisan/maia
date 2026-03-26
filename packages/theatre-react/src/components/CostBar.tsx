/**
 * CostBar — live running cost counter for the current agent run.
 * Shows total tokens, USD cost, and per-agent breakdown.
 */
import React from "react";
import type { ACPEvent, ACPActivity } from "@maia/acp";

export interface CostBarProps {
  events: ACPEvent[];
  budgetUsd?: number;
  className?: string;
}

interface AgentCost {
  tokens: number;
  usd: number;
}

export function CostBar({ events, budgetUsd, className = "" }: CostBarProps) {
  const agentCosts = new Map<string, AgentCost>();
  let totalTokens = 0;
  let totalUsd = 0;

  for (const event of events) {
    if (event.event_type === "event") {
      const act = event.payload as unknown as ACPActivity;
      if (act?.cost) {
        const agentId = act.agent_id ?? event.agent_id;
        const prev = agentCosts.get(agentId) ?? { tokens: 0, usd: 0 };
        prev.tokens += act.cost.tokens_used ?? 0;
        prev.usd += act.cost.cost_usd ?? 0;
        agentCosts.set(agentId, prev);
        totalTokens += act.cost.tokens_used ?? 0;
        totalUsd += act.cost.cost_usd ?? 0;
      }
    }
  }

  const budgetPercent = budgetUsd ? Math.min(100, (totalUsd / budgetUsd) * 100) : 0;
  const overBudget = budgetUsd ? totalUsd > budgetUsd : false;

  return (
    <div className={`flex items-center gap-4 rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900 ${className}`}>
      {/* Total cost */}
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-gray-400">Cost</span>
        <span className={`text-[13px] font-semibold ${overBudget ? "text-red-500" : "text-gray-700 dark:text-gray-200"}`}>
          ${totalUsd.toFixed(4)}
        </span>
      </div>

      {/* Tokens */}
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-gray-400">Tokens</span>
        <span className="text-[13px] font-medium text-gray-600 dark:text-gray-300">
          {totalTokens.toLocaleString()}
        </span>
      </div>

      {/* Budget bar */}
      {budgetUsd !== undefined && budgetUsd > 0 && (
        <div className="flex items-center gap-1.5">
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className={`h-full rounded-full transition-all ${
                overBudget ? "bg-red-500" : budgetPercent > 80 ? "bg-yellow-500" : "bg-green-500"
              }`}
              style={{ width: `${budgetPercent}%` }}
            />
          </div>
          <span className="text-[10px] text-gray-400">
            ${budgetUsd.toFixed(2)} budget
          </span>
        </div>
      )}

      {/* Per-agent breakdown (collapsed) */}
      {agentCosts.size > 1 && (
        <div className="flex gap-2">
          {Array.from(agentCosts.entries()).map(([agentId, cost]) => (
            <span
              key={agentId}
              className="text-[10px] text-gray-400"
              title={`${agentId}: $${cost.usd.toFixed(4)}`}
            >
              {agentId.replace("agent://", "")}: ${cost.usd.toFixed(3)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
