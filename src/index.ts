import { config } from "./config.js";
import { simulateDecision } from "./simulator.js";
import type { MarketSignal, PortfolioState } from "./types.js";

const demoSignal: MarketSignal = {
  symbol: "SOL/USDC",
  side: "BUY",
  confidence: 0.78,
  priceUsd: 150,
  rationale: "Signal fictif de démonstration - aucune donnée de marché réelle.",
};

const portfolio: PortfolioState = {
  capitalUsd: config.simulatedCapitalUsd,
  dailyPnlUsd: 0,
  openPositions: 0,
};

const record = await simulateDecision(demoSignal, portfolio, config.risk);

console.log("JarvisDegen MVP - MODE SIMULATION");
console.log(JSON.stringify(record, null, 2));
