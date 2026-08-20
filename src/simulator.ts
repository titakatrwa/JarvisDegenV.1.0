import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";
import { evaluateRisk } from "./risk-engine.js";
import type { MarketSignal, PortfolioState, RiskLimits, SimulationRecord } from "./types.js";

export async function simulateDecision(
  signal: MarketSignal,
  portfolio: PortfolioState,
  limits: RiskLimits,
  logPath = "logs/simulations.jsonl",
): Promise<SimulationRecord> {
  const record: SimulationRecord = {
    id: randomUUID(),
    timestamp: new Date().toISOString(),
    mode: "SIMULATION",
    signal,
    decision: evaluateRisk(signal, portfolio, limits),
  };

  await mkdir(dirname(logPath), { recursive: true });
  await appendFile(logPath, `${JSON.stringify(record)}\n`, "utf8");
  return record;
}
