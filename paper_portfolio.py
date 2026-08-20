"""Portefeuille paper trading persistant, sans capacité de transaction réelle."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_DB = Path(__file__).parent / "data" / "portfolio.db"
INITIAL_CASH = 10_000.0
FEE_RATE = 0.003
SLIPPAGE_RATE = 0.002
STOP_LOSS_RATE = 0.05
TAKE_PROFIT_RATE = 0.10


def _ensure_column(connection: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cash REAL NOT NULL,
            realized_pnl REAL NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO account (id, cash, realized_pnl) VALUES (1, 10000, 0);
        CREATE TABLE IF NOT EXISTS positions (
            market TEXT PRIMARY KEY,
            quantity REAL NOT NULL,
            average_price REAL NOT NULL,
            last_price REAL NOT NULL,
            opened_at TEXT NOT NULL,
            stop_loss_price REAL,
            take_profit_price REAL
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            market TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            notional REAL NOT NULL,
            realized_pnl REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS equity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event TEXT NOT NULL,
            cash REAL NOT NULL,
            exposure REAL NOT NULL,
            equity REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_pnl REAL NOT NULL
        );
        """
    )
    _ensure_column(connection, "trades", "observed_price", "REAL")
    _ensure_column(connection, "trades", "fees", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "trades", "slippage", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "positions", "stop_loss_price", "REAL")
    _ensure_column(connection, "positions", "take_profit_price", "REAL")
    connection.execute(
        "UPDATE positions SET stop_loss_price = average_price * ? WHERE stop_loss_price IS NULL",
        (1 - STOP_LOSS_RATE,),
    )
    connection.execute(
        "UPDATE positions SET take_profit_price = average_price * ? WHERE take_profit_price IS NULL",
        (1 + TAKE_PROFIT_RATE,),
    )
    if connection.execute("SELECT COUNT(*) FROM equity_history").fetchone()[0] == 0:
        _record_equity(connection, "INITIALISATION", datetime.now(UTC).isoformat())
    connection.commit()
    return connection


def _record_equity(connection: sqlite3.Connection, event: str, timestamp: str) -> None:
    account = connection.execute("SELECT cash, realized_pnl FROM account WHERE id = 1").fetchone()
    positions = connection.execute(
        "SELECT quantity, average_price, last_price FROM positions"
    ).fetchall()
    exposure = sum(row["quantity"] * row["last_price"] for row in positions)
    unrealized = sum(
        (row["last_price"] - row["average_price"]) * row["quantity"]
        for row in positions
    )
    connection.execute(
        "INSERT INTO equity_history (timestamp, event, cash, exposure, equity, realized_pnl, unrealized_pnl) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            timestamp,
            event,
            account["cash"],
            exposure,
            account["cash"] + exposure,
            account["realized_pnl"],
            unrealized,
        ),
    )


def apply_decision(record: dict, db_path: Path = DEFAULT_DB) -> dict:
    """Applique une décision approuvée au portefeuille et retourne sa trace enrichie."""
    result = dict(record)
    if result.get("statut") != "APPROUVÉ" or result.get("action") == "WAIT":
        result["mouvement_portefeuille"] = "AUCUN"
        return result

    market = str(result["marché"])
    side = str(result["action"]).upper()
    price = float(result["prix_usd"])
    now = datetime.now(UTC).isoformat()
    with _connect(db_path) as connection:
        account = connection.execute("SELECT cash FROM account WHERE id = 1").fetchone()
        position = connection.execute(
            "SELECT * FROM positions WHERE market = ?", (market,)
        ).fetchone()

        if side == "BUY":
            notional = float(result.get("position_usd", 0))
            execution_price = price * (1 + SLIPPAGE_RATE)
            fees = notional * FEE_RATE
            total_cost = notional + fees
            if notional <= 0 or account["cash"] < total_cost:
                result.update(
                    statut="REFUSÉ",
                    raison="Cash simulé insuffisant",
                    position_usd=0.0,
                    mouvement_portefeuille="REFUSÉ",
                )
                return result
            quantity = notional / execution_price
            acquisition_cost = total_cost
            if position:
                total_quantity = position["quantity"] + quantity
                average_price = (
                    position["quantity"] * position["average_price"] + acquisition_cost
                ) / total_quantity
                connection.execute(
                    "UPDATE positions SET quantity = ?, average_price = ?, last_price = ?, "
                    "stop_loss_price = ?, take_profit_price = ? WHERE market = ?",
                    (
                        total_quantity, average_price, price,
                        average_price * (1 - STOP_LOSS_RATE),
                        average_price * (1 + TAKE_PROFIT_RATE), market,
                    ),
                )
            else:
                connection.execute(
                    "INSERT INTO positions (market, quantity, average_price, last_price, opened_at, "
                    "stop_loss_price, take_profit_price) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        market, quantity, acquisition_cost / quantity, price, now,
                        acquisition_cost / quantity * (1 - STOP_LOSS_RATE),
                        acquisition_cost / quantity * (1 + TAKE_PROFIT_RATE),
                    ),
                )
            connection.execute("UPDATE account SET cash = cash - ? WHERE id = 1", (total_cost,))
            realized = 0.0
        elif side == "SELL":
            if not position:
                result.update(
                    statut="REFUSÉ",
                    raison="Aucune position simulée à vendre",
                    position_usd=0.0,
                    mouvement_portefeuille="REFUSÉ",
                )
                return result
            quantity = float(position["quantity"])
            execution_price = price * (1 - SLIPPAGE_RATE)
            notional = quantity * execution_price
            fees = notional * FEE_RATE
            proceeds = notional - fees
            realized = proceeds - position["average_price"] * quantity
            connection.execute("DELETE FROM positions WHERE market = ?", (market,))
            connection.execute(
                "UPDATE account SET cash = cash + ?, realized_pnl = realized_pnl + ? WHERE id = 1",
                (proceeds, realized),
            )
            result["position_usd"] = round(notional, 2)
            result["pnl_réalisé_usd"] = round(realized, 2)
        else:
            result["mouvement_portefeuille"] = "AUCUN"
            return result

        slippage = abs(execution_price - price) * quantity
        connection.execute(
            "INSERT INTO trades (timestamp, market, side, quantity, price, notional, realized_pnl, "
            "observed_price, fees, slippage) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, market, side, quantity, execution_price, notional, realized, price, fees, slippage),
        )
        _record_equity(connection, side, now)
    result["prix_exécution_usd"] = round(execution_price, 8)
    result["frais_usd"] = round(fees, 4)
    result["slippage_usd"] = round(slippage, 4)
    result["mouvement_portefeuille"] = side
    return result


def update_prices(prices: dict[str, float], db_path: Path = DEFAULT_DB) -> None:
    with _connect(db_path) as connection:
        for market, price in prices.items():
            connection.execute(
                "UPDATE positions SET last_price = ? WHERE market = ?",
                (float(price), market),
            )
        _record_equity(connection, "VALORISATION", datetime.now(UTC).isoformat())


def get_portfolio(db_path: Path = DEFAULT_DB) -> dict:
    with _connect(db_path) as connection:
        account = dict(connection.execute("SELECT * FROM account WHERE id = 1").fetchone())
        positions = [dict(row) for row in connection.execute("SELECT * FROM positions ORDER BY market")]
        trades = [
            dict(row)
            for row in connection.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 100")
        ]
        history = [
            dict(row)
            for row in connection.execute("SELECT * FROM equity_history ORDER BY id")
        ]
    for position in positions:
        position["valeur_usd"] = position["quantity"] * position["last_price"]
        position["pnl_latent_usd"] = (
            position["last_price"] - position["average_price"]
        ) * position["quantity"]
        if position["last_price"] <= position["stop_loss_price"]:
            position["protection"] = "STOP À EXAMINER"
        elif position["last_price"] >= position["take_profit_price"]:
            position["protection"] = "OBJECTIF ATTEINT"
        else:
            position["protection"] = "DANS LES LIMITES"
    exposure = sum(position["valeur_usd"] for position in positions)
    unrealized = sum(position["pnl_latent_usd"] for position in positions)
    return {
        "cash": account["cash"],
        "realized_pnl": account["realized_pnl"],
        "unrealized_pnl": unrealized,
        "exposure": exposure,
        "equity": account["cash"] + exposure,
        "positions": positions,
        "trades": trades,
        "history": history,
    }
