from unittest.mock import Mock, patch

from market_data import fetch_market_snapshot, fetch_solana_status


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_selects_most_liquid_stable_pair():
    pairs = [
        {
            "chainId": "solana",
            "dexId": "small-dex",
            "baseToken": {"symbol": "SOL"},
            "quoteToken": {"symbol": "USDC"},
            "priceUsd": "80",
            "priceChange": {"h24": 1},
            "volume": {"h24": 100},
            "liquidity": {"usd": 1_000},
            "url": "https://example.com/small",
        },
        {
            "chainId": "solana",
            "dexId": "deep-dex",
            "baseToken": {"symbol": "SOL"},
            "quoteToken": {"symbol": "USDC"},
            "priceUsd": "81",
            "priceChange": {"h24": 2},
            "volume": {"h24": 500},
            "liquidity": {"usd": 9_000},
            "url": "https://example.com/deep",
        },
    ]
    with patch("market_data.requests.get", return_value=_response(pairs)):
        snapshot = fetch_market_snapshot("SOL/USDC")
    assert snapshot["dex"] == "deep-dex"
    assert snapshot["price_usd"] == 81


def test_reads_rpc_health_and_finalized_slot():
    payload = [
        {"jsonrpc": "2.0", "id": 1, "result": "ok"},
        {"jsonrpc": "2.0", "id": 2, "result": 123456},
    ]
    with patch("market_data.requests.post", return_value=_response(payload)):
        status = fetch_solana_status()
    assert status == {
        "healthy": True,
        "slot": 123456,
        "source": "Solana mainnet-beta RPC",
    }
