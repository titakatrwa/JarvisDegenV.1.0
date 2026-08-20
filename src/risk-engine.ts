import type { MarketSignal, PortfolioState, RiskDecision, RiskLimits } from "./types.js";

export function evaluateRisk(
  signal: MarketSignal,
  portfolio: PortfolioState,
  limits: RiskLimits,
): RiskDecision {
  if (signal.confidence < limits.minConfidence) {
    return { approved: false, reason: "Confiance du signal insuffisante" };
  }

  if (portfolio.openPositions >= limits.maxOpenPositions) {
    return { approved: false, reason: "Nombre maximal de positions ouvertes atteint" };
  }

  const dailyLossLimitUsd = portfolio.capitalUsd * (limits.maxDailyLossPercent / 100);
  if (portfolio.dailyPnlUsd <= -dailyLossLimitUsd) {
    return { approved: false, reason: "Limite de perte journalière atteinte" };
  }

  const positionSizeUsd = portfolio.capitalUsd * (limits.maxPositionPercent / 100);
  return { approved: true, positionSizeUsd: Number(positionSizeUsd.toFixed(2)) };
}
