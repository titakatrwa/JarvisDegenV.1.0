export type TradeSide = "BUY" | "SELL";

export interface MarketSignal {
  symbol: string;
  side: TradeSide;
  confidence: number;
  priceUsd: number;
  rationale: string;
}

export interface PortfolioState {
  capitalUsd: number;
  dailyPnlUsd: number;
  openPositions: number;
}

export interface RiskLimits {
  maxPositionPercent: number;
  maxDailyLossPercent: number;
  maxOpenPositions: number;
  minConfidence: number;
}

export type RiskDecision =
  | { approved: true; positionSizeUsd: number }
  | { approved: false; reason: string };

export interface SimulationRecord {
  id: string;
  timestamp: string;
  mode: "SIMULATION";
  signal: MarketSignal;
  decision: RiskDecision;
}
