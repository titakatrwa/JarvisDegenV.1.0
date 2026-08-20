import type { RiskLimits } from "./types.js";

function numberFromEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${name} doit être un nombre valide.`);
  return value;
}

const simulationMode = (process.env.SIMULATION_MODE ?? "true").toLowerCase() === "true";

if (!simulationMode) {
  throw new Error(
    "Sécurité étape 1 : SIMULATION_MODE doit rester à true. Le trading réel n'est pas implémenté.",
  );
}

export const config = {
  simulationMode,
  simulatedCapitalUsd: numberFromEnv("SIMULATED_CAPITAL_USD", 10_000),
  retradingShare: numberFromEnv("RETRADING_SHARE", 0.7),
  buybackBurnShare: numberFromEnv("BUYBACK_BURN_SHARE", 0.3),
  risk: {
    maxPositionPercent: numberFromEnv("MAX_POSITION_PERCENT", 2),
    maxDailyLossPercent: numberFromEnv("MAX_DAILY_LOSS_PERCENT", 3),
    maxOpenPositions: numberFromEnv("MAX_OPEN_POSITIONS", 3),
    minConfidence: numberFromEnv("MIN_CONFIDENCE", 0.7),
  } satisfies RiskLimits,
};

if (Math.abs(config.retradingShare + config.buybackBurnShare - 1) > 0.000001) {
  throw new Error("RETRADING_SHARE + BUYBACK_BURN_SHARE doit être égal à 1.");
}
