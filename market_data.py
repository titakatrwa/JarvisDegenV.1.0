"""Accès strictement en lecture seule aux données publiques Solana."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import requests


DEXSCREENER_BASE = "https://api.dexscreener.com"
GECKOTERMINAL_BASE = "https://api.geckoterminal.com/api/v2"
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
REQUEST_TIMEOUT = 8

TOKENS = {
    "SOL/USDC": {
        "symbol": "SOL",
        "mint": "So11111111111111111111111111111111111111112",
    },
    "JUP/USDC": {
        "symbol": "JUP",
        "mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    },
    "BONK/USDC": {
        "symbol": "BONK",
        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6G77WxjB1pPB263",
    },
}


@dataclass(frozen=True)
class MarketSnapshot:
    market: str
    price_usd: float
    change_24h: float
    volume_24h: float
    liquidity_usd: float
    dex: str
    pair_url: str
    pair_address: str
    source: str = "DEX Screener"


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def fetch_market_snapshot(market: str) -> dict[str, Any]:
    """Retourne la paire Solana la plus liquide pour le marché demandé."""
    token = TOKENS.get(market)
    if token is None:
        raise ValueError(f"Marché non pris en charge : {market}")

    response = requests.get(
        f"{DEXSCREENER_BASE}/token-pairs/v1/solana/{token['mint']}",
        headers={"Accept": "application/json", "User-Agent": "JarvisDegen-MVP/0.2"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    pairs = response.json()
    if not isinstance(pairs, list):
        raise RuntimeError("Réponse marché inattendue")

    stable_quotes = {"USDC", "USDT"}
    candidates = [
        pair
        for pair in pairs
        if pair.get("chainId") == "solana"
        and pair.get("baseToken", {}).get("symbol", "").upper() == token["symbol"]
        and pair.get("quoteToken", {}).get("symbol", "").upper() in stable_quotes
        and _number(pair.get("priceUsd")) > 0
    ]
    if not candidates:
        raise RuntimeError(f"Aucune paire liquide trouvée pour {market}")

    pair = max(candidates, key=lambda item: _number(item.get("liquidity", {}).get("usd")))
    snapshot = MarketSnapshot(
        market=market,
        price_usd=_number(pair.get("priceUsd")),
        change_24h=_number(pair.get("priceChange", {}).get("h24")),
        volume_24h=_number(pair.get("volume", {}).get("h24")),
        liquidity_usd=_number(pair.get("liquidity", {}).get("usd")),
        dex=str(pair.get("dexId") or "inconnu"),
        pair_url=str(pair.get("url") or ""),
        pair_address=str(pair.get("pairAddress") or ""),
    )
    return asdict(snapshot)


def fetch_ohlcv(pair_address: str, limit: int = 180) -> list[dict[str, Any]]:
    """Charge des bougies de quatre heures depuis GeckoTerminal."""
    if not pair_address or not 30 <= limit <= 1_000:
        raise ValueError("Adresse de pool ou limite OHLCV invalide")
    response = requests.get(
        f"{GECKOTERMINAL_BASE}/networks/solana/pools/{pair_address}/ohlcv/hour",
        params={"aggregate": 4, "limit": limit, "currency": "usd", "token": "base"},
        headers={
            "Accept": "application/json;version=20230203",
            "User-Agent": "JarvisDegen-MVP/0.3",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    rows = response.json().get("data", {}).get("attributes", {}).get("ohlcv_list", [])
    candles = [
        {
            "timestamp": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
        if len(row) >= 6
    ]
    candles.sort(key=lambda candle: candle["timestamp"])
    if len(candles) < 20:
        raise RuntimeError("Historique insuffisant pour le backtest")
    return candles


def fetch_solana_status() -> dict[str, Any]:
    """Lit la santé et le slot courant d'un RPC Solana public."""
    payload = [
        {"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
        {"jsonrpc": "2.0", "id": 2, "method": "getSlot", "params": [{"commitment": "finalized"}]},
    ]
    response = requests.post(
        SOLANA_RPC_URL,
        json=payload,
        headers={"Content-Type": "application/json", "User-Agent": "JarvisDegen-MVP/0.2"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    results = {item.get("id"): item for item in response.json()}
    return {
        "healthy": results.get(1, {}).get("result") == "ok",
        "slot": int(results.get(2, {}).get("result", 0)),
        "source": "Solana mainnet-beta RPC",
    }
