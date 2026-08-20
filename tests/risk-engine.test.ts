import { describe, expect, it } from "vitest";
import { evaluateRisk } from "../src/risk-engine.js";
import type { MarketSignal, PortfolioState, RiskLimits } from "../src/types.js";

const limits: RiskLimits = {
  maxPositionPercent: 2,
  maxDailyLossPercent: 3,
  maxOpenPositions: 3,
  minConfidence: 0.7,
};
const signal: MarketSignal = {
  symbol: "SOL/USDC",
  side: "BUY",
  confidence: 0.8,
  priceUsd: 150,
  rationale: "test",
};
const portfolio: PortfolioState = {
  capitalUsd: 10_000,
  dailyPnlUsd: 0,
  openPositions: 0,
};

describe("evaluateRisk", () => {
  it("limite une position à 2 % du capital", () => {
    expect(evaluateRisk(signal, portfolio, limits)).toEqual({
      approved: true,
      positionSizeUsd: 200,
    });
  });

  it("refuse un signal trop peu fiable", () => {
    expect(evaluateRisk({ ...signal, confidence: 0.69 }, portfolio, limits)).toMatchObject({
      approved: false,
    });
  });

  it("coupe les décisions après la perte journalière maximale", () => {
    expect(evaluateRisk(signal, { ...portfolio, dailyPnlUsd: -300 }, limits)).toMatchObject({
      approved: false,
    });
  });

  it("refuse une position quand le portefeuille est déjà plein", () => {
    expect(evaluateRisk(signal, { ...portfolio, openPositions: 3 }, limits)).toMatchObject({
      approved: false,
    });
  });
});
