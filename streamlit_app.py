"""Tableau de bord visible du MVP JarvisDegen, exclusivement en simulation."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from audit_store import append_record, export_json, list_records, verify_chain
from backtest import (
    analyze_parameter_sensitivity,
    analyze_market_regimes,
    compare_signal_confirmations,
    compare_signal_strength_filters,
    compare_volume_filters,
    compare_strategies,
    run_backtest,
    stress_execution_costs,
    summarize_validation_readiness,
    validate_out_of_sample,
    validate_confirmation_out_of_sample,
    validate_strength_filter_out_of_sample,
    validate_volume_filter_out_of_sample,
    validate_volume_filter_walk_forward,
    validate_strength_filter_walk_forward,
    validate_confirmation_walk_forward,
    validate_walk_forward,
)
from backtest_report import build_backtest_report, export_backtest_report, inspect_backtest_report
from backtest_report_store import (
    archive_backtest_report,
    list_backtest_reports,
    summarize_backtest_history,
    verify_backtest_archive,
)
from data_quality import assess_ohlcv_quality
from launch_audit import run_launch_audit
from lifecycle import (assess_paper_drift, build_supervised_paper_policy,
                       evaluate_market_dataset, select_candidate,
                       summarize_cross_market)
from market_data import TOKENS, fetch_market_snapshot, fetch_ohlcv, fetch_solana_status
from market_scanner import rank_markets
from paper_portfolio import apply_decision, get_portfolio, update_prices
from performance_metrics import calculate_performance
from risk_monitor import calculate_risk
from review_guard import validate_review
from scanner_store import append_scan, export_history, list_observations, scan_count, signal_confirmations
from signal_alerts import build_alerts, export_alerts
from social_content import TONES, generate_social_drafts
from strategy import analyse_market
from surveillance import INTERVALS, scan_is_due
from trade_bootstrap import bootstrap_trade_outcomes


ROOT = Path(__file__).parent
AVATAR = ROOT / "avatar_JDEGEN.png"
LOG_PATH = ROOT / "logs" / "dashboard_simulations.jsonl"

st.set_page_config(
    page_title="JarvisDegen — simulation",
    page_icon=":material/smart_toy:",
    layout="wide",
)


def initialise_state() -> None:
    portfolio = get_portfolio()
    risk = calculate_risk(portfolio)
    defaults = {
        "capital": portfolio["equity"],
        "daily_pnl": risk["daily_change"],
        "open_positions": len(portfolio["positions"]),
        "decisions": list_records(),
        "current_analysis": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_data(ttl=60, max_entries=10, show_spinner=False)
def load_market_snapshot(market: str) -> dict:
    return fetch_market_snapshot(market)


@st.cache_data(ttl=30, max_entries=2, show_spinner=False)
def load_solana_status() -> dict:
    return fetch_solana_status()


@st.cache_data(ttl=300, max_entries=10, show_spinner=False)
def load_ohlcv(pair_address: str, limit: int) -> list[dict]:
    return fetch_ohlcv(pair_address, limit)


@st.cache_data(ttl=900, max_entries=4, show_spinner=False)
def run_cross_market_validation(limit: int = 300) -> dict:
    results, failures = [], []
    for market in TOKENS:
        try:
            snapshot = fetch_market_snapshot(market)
            candles = fetch_ohlcv(snapshot["pair_address"], limit)
            results.append(evaluate_market_dataset(market, candles))
        except Exception as exc:
            failures.append({"marché": market, "raison": str(exc)})
    return summarize_cross_market(results, failures)


def run_scanner_cycle() -> dict:
    snapshots = []
    failures = []
    for watched_market in TOKENS:
        try:
            snapshots.append(load_market_snapshot(watched_market))
        except Exception as exc:
            failures.append(f"{watched_market} : {exc}")
    results = rank_markets(snapshots)
    saved = append_scan(results) if results else None
    return {"results": results, "failures": failures, "saved": saved}


def store_scanner_cycle(cycle: dict) -> None:
    st.session_state["scanner_results"] = cycle["results"]
    st.session_state["scanner_failures"] = cycle["failures"]
    if cycle["saved"]:
        timestamp = cycle["saved"]["timestamp"]
        st.session_state["scanner_time"] = datetime.fromisoformat(timestamp).strftime(
            "%H:%M:%S UTC"
        )


def evaluate_signal(
    confidence: float, max_position: float, action: str, market: str
) -> tuple[str, str, float]:
    if confidence < 0.70:
        return "REFUSÉ", "Confiance inférieure à 70 %", 0.0
    risk = calculate_risk(get_portfolio())
    if action == "BUY" and risk["halted"]:
        return "REFUSÉ", "Coupe-circuit : perte journalière maximale atteinte", 0.0
    if max_position > 2.0:
        return "REFUSÉ", "La position maximale autorisée est de 2 %", 0.0
    open_markets = {position["market"] for position in get_portfolio()["positions"]}
    if action == "BUY" and market in open_markets:
        return "REFUSÉ", "Une position simulée est déjà ouverte sur ce marché", 0.0
    if action == "BUY" and st.session_state.open_positions >= 3:
        return "REFUSÉ", "Trois positions sont déjà ouvertes", 0.0
    position = st.session_state.capital * (max_position / 100)
    return "APPROUVÉ", "Tous les garde-fous sont respectés", round(position, 2)


def persist_decision(record: dict, analysis: dict | None = None) -> dict:
    record = apply_decision(record)
    portfolio = get_portfolio()
    risk = calculate_risk(portfolio)
    st.session_state.capital = portfolio["equity"]
    st.session_state.daily_pnl = risk["daily_change"]
    st.session_state.open_positions = len(portfolio["positions"])
    if analysis is not None:
        st.session_state.current_analysis = analysis
    stored_record = append_record(record)
    st.session_state.decisions.insert(0, stored_record)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    st.toast(
        f"Décision {record['statut'].lower()} — aucune transaction réelle",
        icon=":material/shield:",
    )
    return record


def simulate(symbol: str, analysis: dict, max_position: float, price_usd: float) -> None:
    side = analysis["action"]
    confidence = analysis["confidence"]
    if side == "WAIT":
        status, reason, size = "OBSERVATION", "La stratégie ne détecte pas de signal assez fort", 0.0
    else:
        status, reason, size = evaluate_signal(confidence, max_position, side, symbol)
    persist_decision(
        {
            "heure": datetime.now(UTC).strftime("%H:%M:%S UTC"),
            "marché": symbol,
            "action": side,
            "confiance": confidence,
            "score": analysis["score"],
            "prix_usd": price_usd,
            "statut": status,
            "position_usd": size,
            "raison": reason,
        },
        analysis,
    )


def candlestick_chart(candles: pd.DataFrame) -> alt.LayerChart:
    """Construit des chandeliers OHLC avec les deux moyennes du backtest."""
    data = candles.copy()
    data["direction"] = data.apply(
        lambda row: "Hausse" if row["close"] >= row["open"] else "Baisse", axis=1
    )
    color = alt.Color(
        "direction:N",
        scale=alt.Scale(domain=["Hausse", "Baisse"], range=["#20D99A", "#FF5C72"]),
        legend=alt.Legend(title=None, orient="bottom"),
    )
    base = alt.Chart(data).encode(
        x=alt.X("date:T", title=None),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%d/%m %H:%M"),
            alt.Tooltip("open:Q", title="Ouverture", format=".6f"),
            alt.Tooltip("high:Q", title="Plus haut", format=".6f"),
            alt.Tooltip("low:Q", title="Plus bas", format=".6f"),
            alt.Tooltip("close:Q", title="Clôture", format=".6f"),
            alt.Tooltip("volume:Q", title="Volume", format=",.0f"),
        ],
    )
    wicks = base.mark_rule().encode(
        y=alt.Y("low:Q", title="Prix ($)", scale=alt.Scale(zero=False)),
        y2="high:Q",
        color=color,
    )
    bodies = base.mark_bar(size=5).encode(
        y=alt.Y("open:Q", title="Prix ($)", scale=alt.Scale(zero=False)),
        y2="close:Q",
        color=color,
    )
    moving = data.melt(
        id_vars=["date"],
        value_vars=["moyenne_courte", "moyenne_longue"],
        var_name="moyenne",
        value_name="prix",
    ).dropna()
    averages = (
        alt.Chart(moving)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("prix:Q", title="Prix ($)", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "moyenne:N",
                scale=alt.Scale(
                    domain=["moyenne_courte", "moyenne_longue"],
                    range=["#4CA9FF", "#FFB454"],
                ),
                legend=alt.Legend(title=None, orient="bottom"),
            ),
        )
    )
    return alt.layer(wicks, bodies, averages).properties(height=420).interactive(bind_y=False)


def capital_chart(equity: pd.DataFrame) -> alt.LayerChart:
    """Courbe de capital lisible même lorsque les variations sont faibles."""
    base = alt.Chart(equity).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y(
            "capital:Q",
            title="Capital simulé ($)",
            scale=alt.Scale(zero=False, padding=20),
        ),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%d/%m %H:%M"),
            alt.Tooltip("capital:Q", title="Capital", format="$,.2f"),
        ],
    )
    line = base.mark_line(color="#12D9CF", strokeWidth=3)
    points = base.mark_point(color="#12D9CF", filled=True, size=28, opacity=0.65)
    return alt.layer(line, points).properties(height=320).interactive(bind_y=False)


def capital_comparison_chart(curves: pd.DataFrame) -> alt.Chart:
    """Compare les capitaux avec une échelle resserrée et des infobulles."""
    return (
        alt.Chart(curves)
        .mark_line(strokeWidth=2.5)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y(
                "capital:Q",
                title="Capital simulé ($)",
                scale=alt.Scale(zero=False, padding=20),
            ),
            color=alt.Color("stratégie:N", title=None, legend=alt.Legend(orient="bottom")),
            tooltip=[
                alt.Tooltip("date:T", title="Date", format="%d/%m %H:%M"),
                alt.Tooltip("stratégie:N", title="Stratégie"),
                alt.Tooltip("capital:Q", title="Capital", format="$,.2f"),
            ],
        )
        .properties(height=360)
        .interactive(bind_y=False)
    )


initialise_state()


@st.fragment(
    run_every="60s" if st.session_state.get("auto_scanner_enabled", False) else None
)
def automatic_scanner() -> None:
    if not st.session_state.get("auto_scanner_enabled", False):
        st.badge("Surveillance automatique désactivée", icon=":material/pause:", color="gray")
        return
    interval_label = st.session_state.get("auto_scanner_interval", "5 min")
    interval_minutes = INTERVALS.get(interval_label, 5)
    last_attempt = st.session_state.get("last_auto_scan")
    if scan_is_due(last_attempt, interval_minutes):
        with st.status("Cycle de surveillance en cours…", expanded=False) as status:
            cycle = run_scanner_cycle()
            store_scanner_cycle(cycle)
            st.session_state["last_auto_scan"] = datetime.now(UTC).isoformat()
            if cycle["results"]:
                status.update(
                    label=f"Cycle enregistré • {len(cycle['results'])} marché(s)",
                    state="complete",
                )
            else:
                status.update(label="Aucun marché disponible", state="error")
        st.rerun()
    else:
        last_time = datetime.fromisoformat(last_attempt).strftime("%H:%M:%S UTC")
        st.badge(
            f"Surveillance active • toutes les {interval_minutes} min",
            icon=":material/autorenew:",
            color="green",
        )
        st.caption(f"Dernière tentative automatique : {last_time}")


with st.sidebar:
    st.image(str(AVATAR), width="stretch")
    st.subheader("Console de simulation")
    st.badge("Simulation active", icon=":material/science:", color="green")
    st.caption("Aucun wallet connecté. Aucune transaction ne peut être envoyée.")

    with st.form("simulation_controls", border=True):
        symbol = st.selectbox("Marché observé", list(TOKENS))
        max_position = st.slider("Position maximale", 0.5, 2.0, 2.0, 0.5, format="%.1f %%")
        submitted = st.form_submit_button(
            "Analyser et simuler",
            icon=":material/play_arrow:",
            type="primary",
            width="stretch",
        )
        if submitted:
            try:
                fresh_snapshot = load_market_snapshot(symbol)
                analysis = analyse_market(fresh_snapshot)
                simulate(symbol, analysis, max_position, fresh_snapshot["price_usd"])
            except Exception as exc:
                st.error(f"Analyse impossible : {exc}", icon=":material/error:")

hero_text, hero_visual = st.columns([1.15, 1], vertical_alignment="center")
with hero_text:
    st.title("JarvisDegen", text_alignment="left")
    st.markdown("## L’IA de trading qui publie chaque décision")
    st.write(
        "Un agent expérimental sur Solana, conçu pour analyser, décider et rendre "
        "ses actions auditables par toute la communauté."
    )
    st.markdown(
        ":green-badge[Simulation active] :blue-badge[Solana] "
        ":orange-badge[$JDEGEN en conception]"
    )
    st.caption("MVP local — aucune promesse de rendement, aucun wallet connecté.")
with hero_visual:
    st.image(str(AVATAR), width="stretch")

live_tab, scanner_tab, portfolio_tab, performance_tab, backtest_tab, social_tab, audit_tab, concept_tab, tokenomics_tab, roadmap_tab = st.tabs(
    ["Agent live", "Scanner", "Portefeuille paper", "Performance", "Backtest", "Réseaux sociaux", "Centre de contrôle", "Le concept", "Tokenomics", "Feuille de route"]
)

with live_tab:
    st.subheader("Console opérationnelle", anchor=False)
    st.caption(
        "Prix, volume et liquidité sont lus publiquement. Les décisions et le portefeuille restent simulés."
    )

    try:
        with st.skeleton(height=130):
            market_snapshot = load_market_snapshot(symbol)
        st.markdown(":green-badge[Données marché en direct] :blue-badge[Lecture seule]")
        with st.container(horizontal=True):
            st.metric(
                f"Prix {symbol}",
                f"${market_snapshot['price_usd']:,.6f}",
                f"{market_snapshot['change_24h']:+.2f} % sur 24 h",
                border=True,
            )
            st.metric(
                "Volume sur 24 h",
                f"${market_snapshot['volume_24h']:,.0f}",
                border=True,
            )
            st.metric(
                "Liquidité de la paire",
                f"${market_snapshot['liquidity_usd']:,.0f}",
                border=True,
            )
            st.metric("DEX", market_snapshot["dex"].upper(), border=True)
        st.caption(
            f"Source : {market_snapshot['source']} • cache 60 secondes • "
            f"[ouvrir la paire]({market_snapshot['pair_url']})"
        )
    except Exception as exc:
        market_snapshot = None
        st.warning(
            "La source de marché est momentanément indisponible. "
            "La console de simulation reste utilisable sans prix en direct.",
            icon=":material/cloud_off:",
        )
        st.caption(f"Détail technique : {exc}")

    with st.container(horizontal=True):
        st.metric(
            "Capital virtuel",
            f"${st.session_state.capital:,.0f}",
            "$0 aujourd’hui",
            border=True,
            chart_data=[9_900, 9_940, 9_920, 9_980, 10_000],
            chart_type="line",
        )
        st.metric("Positions ouvertes", f"{st.session_state.open_positions} / 3", border=True)
        st.metric("Risque par position", "2 %", "$200 maximum", border=True)
        st.metric("Perte journalière max.", "3 %", "$300 coupe-circuit", border=True)

    left, right = st.columns([1.35, 1])
    with left.container(border=True, height="stretch"):
        st.subheader("Dernière décision", anchor=False)
        if st.session_state.decisions:
            latest = st.session_state.decisions[0]
            color = "green" if latest["statut"] == "APPROUVÉ" else "red"
            st.badge(latest["statut"].capitalize(), color=color)
            st.metric("Taille simulée", f"${latest['position_usd']:,.2f}")
            st.write(
                f"**{latest['action']} {latest['marché']}** — "
                f"confiance {latest['confiance']:.0%}"
            )
            st.caption(latest["raison"])
        else:
            st.info(
                "Utilise la console à gauche pour produire la première décision visible.",
                icon=":material/touch_app:",
            )

    with right.container(border=True, height="stretch"):
        st.subheader("Raisonnement de Jarvis", anchor=False)
        analysis = st.session_state.current_analysis
        if analysis:
            action_color = {
                "BUY": "green",
                "SELL": "red",
                "WAIT": "orange",
            }[analysis["action"]]
            st.badge(f"Signal {analysis['action']}", color=action_color)
            st.metric("Score stratégique", f"{analysis['score']:+.1f} / 100")
            contributions = pd.DataFrame(
                {
                    "Facteur": list(analysis["contributions"]),
                    "Contribution": list(analysis["contributions"].values()),
                }
            )
            st.bar_chart(contributions, x="Facteur", y="Contribution", horizontal=True)
            st.caption(analysis["rationale"])
        else:
            st.info(
                "Lance une analyse pour afficher le détail du score.",
                icon=":material/psychology:",
            )

    with st.container(border=True):
        st.subheader("État technique", anchor=False)
        with st.container(horizontal=True):
            st.badge("Moteur de risque prêt", icon=":material/check:", color="green")
            st.badge("Journal local actif", icon=":material/check:", color="green")
            st.badge("Exécution on-chain bloquée", icon=":material/lock:", color="orange")
        try:
            network = load_solana_status()
            network_color = "green" if network["healthy"] else "red"
            network_label = "RPC Solana opérationnel" if network["healthy"] else "RPC Solana dégradé"
            st.badge(network_label, icon=":material/hub:", color=network_color)
            st.write(f"**Dernier slot finalisé :** `{network['slot']:,}`")
            st.caption(f"Source : {network['source']} • cache 30 secondes")
        except Exception:
            st.badge("RPC Solana indisponible", icon=":material/cloud_off:", color="red")

    with st.container(border=True):
        st.subheader("Journal d’audit", anchor=False)
        if st.session_state.decisions:
            integrity = verify_chain()
            if integrity["valid"]:
                st.badge(
                    f"Chaîne vérifiée • {integrity['count']} décisions",
                    icon=":material/verified:",
                    color="green",
                )
            else:
                st.badge(
                    f"Intégrité rompue à l’entrée {integrity['broken_at']}",
                    icon=":material/error:",
                    color="red",
                )
            history = pd.DataFrame(st.session_state.decisions)
            if "empreinte" in history:
                history["empreinte_courte"] = history["empreinte"].str[:12] + "…"
            st.dataframe(
                history,
                hide_index=True,
                column_config={
                    "confiance": st.column_config.ProgressColumn(
                        "Confiance", min_value=0, max_value=1, format="percent"
                    ),
                    "position_usd": st.column_config.NumberColumn(
                        "Position", format="$%.2f"
                    ),
                    "prix_usd": st.column_config.NumberColumn(
                        "Prix observé", format="$%.6f"
                    ),
                    "empreinte": None,
                    "empreinte_courte": st.column_config.TextColumn("Empreinte SHA-256"),
                },
            )
            csv_export = history.drop(columns=["empreinte"], errors="ignore").to_csv(
                index=False
            )
            with st.container(horizontal=True):
                st.download_button(
                    "Exporter en CSV",
                    data=csv_export,
                    file_name="jdegen_audit.csv",
                    mime="text/csv",
                    icon=":material/download:",
                )
                st.download_button(
                    "Exporter en JSON",
                    data=export_json(),
                    file_name="jdegen_audit.json",
                    mime="application/json",
                    icon=":material/download:",
                )
            st.caption(
                "Chaque empreinte inclut celle de l’entrée précédente : une modification historique "
                "rend la chaîne invalide."
            )
        else:
            st.caption("Aucune décision enregistrée pour cette session.")

with scanner_tab:
    st.subheader("Scanner multi-marchés", anchor=False)
    st.write(
        "Jarvis compare toute la liste de surveillance avec la même stratégie et les mêmes données. "
        "Le score de priorité combine intensité du signal, confiance et profondeur de liquidité."
    )
    with st.container(border=True):
        st.toggle(
            "Activer la surveillance automatique",
            key="auto_scanner_enabled",
            help="Enregistre des observations uniquement. Aucun ordre paper n’est créé.",
        )
        st.segmented_control(
            "Fréquence",
            options=list(INTERVALS),
            default="5 min",
            key="auto_scanner_interval",
            disabled=not st.session_state.get("auto_scanner_enabled", False),
        )
        automatic_scanner()
    if st.button(
        "Scanner les marchés",
        icon=":material/radar:",
        type="primary",
        key="run_market_scanner",
    ):
        with st.skeleton(height=220):
            store_scanner_cycle(run_scanner_cycle())

    scanner_results = st.session_state.get("scanner_results", [])
    scanner_failures = st.session_state.get("scanner_failures", [])
    scanner_history = list_observations()
    confirmations = signal_confirmations(scanner_history)
    if scanner_results:
        actionable = [row for row in scanner_results if row["action"] != "WAIT"]
        leader = actionable[0] if actionable else scanner_results[0]
        with st.container(border=True):
            st.caption("MARCHÉ PRIORITAIRE DU SCAN")
            with st.container(horizontal=True):
                st.metric("Marché", leader["marché"], border=True)
                st.metric("Signal", leader["action"], border=True)
                st.metric("Score", f"{leader['score']:+.1f}", border=True)
                st.metric("Confiance", f"{leader['confiance']:.0%}", border=True)
                st.metric("Priorité", f"{leader['priorité']:.2f}", border=True)
                leader_confirmation = confirmations.get(leader["marché"], {"cycles": 1})
                st.metric(
                    "Confirmation",
                    f"{leader_confirmation['cycles']} scan(s)",
                    border=True,
                )
            st.write(leader["raison"])

        scanner_frame = pd.DataFrame(scanner_results)
        st.dataframe(
            scanner_frame,
            hide_index=True,
            column_config={
                "marché": st.column_config.TextColumn("Marché", pinned=True),
                "action": st.column_config.TextColumn("Signal"),
                "score": st.column_config.NumberColumn("Score", format="%+.1f"),
                "confiance": st.column_config.ProgressColumn(
                    "Confiance", min_value=0, max_value=1, format="percent"
                ),
                "priorité": st.column_config.NumberColumn("Priorité", format="%.2f"),
                "prix_usd": st.column_config.NumberColumn("Prix", format="$%.6f"),
                "variation_24h": st.column_config.NumberColumn("24 h", format="%+.2f %%"),
                "volume_24h": st.column_config.NumberColumn("Volume 24 h", format="$%.0f"),
                "liquidité_usd": st.column_config.NumberColumn("Liquidité", format="$%.0f"),
                "raison": st.column_config.TextColumn("Explication", width="large"),
                "source": st.column_config.TextColumn("Source"),
            },
        )
        score_chart = scanner_frame[["marché", "score"]].rename(
            columns={"marché": "Marché", "score": "Score"}
        )
        st.bar_chart(score_chart, x="Marché", y="Score", horizontal=True)
        st.caption(
            f"Dernier scan : {st.session_state.get('scanner_time', '—')} • lecture seule • "
            "aucun ordre paper créé."
        )
    else:
        st.info(
            "Lance le scanner pour comparer SOL, JUP et BONK avec des données actuelles.",
            icon=":material/troubleshoot:",
        )
    if scanner_failures:
        with st.expander("Marchés indisponibles", icon=":material/cloud_off:"):
            for failure in scanner_failures:
                st.write(f"- {failure}")
    alert_portfolio = get_portfolio()
    alert_risk = calculate_risk(alert_portfolio)
    signal_alerts = build_alerts(
        scanner_history, confirmations, alert_portfolio, alert_risk
    )
    st.subheader("Centre d’alertes", anchor=False)
    if signal_alerts:
        ready_alerts = [alert for alert in signal_alerts if alert["statut"] == "À EXAMINER"]
        with st.container(horizontal=True):
            st.metric("Alertes actives", len(signal_alerts), border=True)
            st.metric("À examiner", len(ready_alerts), border=True)
            st.metric("Exécution automatique", "Désactivée", border=True)
        for alert in signal_alerts:
            with st.container(border=True):
                status_color = "green" if alert["statut"] == "À EXAMINER" else "orange"
                st.badge(
                    alert["statut"],
                    icon=":material/notifications_active:",
                    color=status_color,
                )
                with st.container(horizontal=True):
                    st.metric("Marché", alert["marché"], border=True)
                    st.metric("Signal", alert["signal"], border=True)
                    st.metric("Score", f"{alert['score']:+.1f}", border=True)
                    st.metric("Confiance", f"{alert['confiance']:.0%}", border=True)
                    st.metric("Confirmations", alert["confirmations"], border=True)
                st.write(alert["motif"])
        st.download_button(
            "Exporter les alertes",
            data=export_alerts(signal_alerts),
            file_name="jdegen_alertes_signaux.json",
            mime="application/json",
            icon=":material/download:",
        )
        st.caption(
            "Une alerte à examiner n’exécute rien : utilise le bouton de simulation principal "
            "pour produire une décision auditée séparée."
        )
        if ready_alerts:
            st.subheader("Soumettre une alerte au moteur paper", anchor=False)
            ready_markets = [alert["marché"] for alert in ready_alerts]
            with st.form("alert_review_form", border=True):
                review_market = st.selectbox("Alerte à examiner", ready_markets)
                review_size = st.slider(
                    "Taille paper maximale",
                    0.5,
                    2.0,
                    1.0,
                    0.5,
                    format="%.1f %%",
                )
                review_acknowledged = st.checkbox(
                    "J’ai relu le signal et je demande une nouvelle vérification du marché."
                )
                review_submitted = st.form_submit_button(
                    "Reconfirmer et soumettre",
                    icon=":material/fact_check:",
                    type="primary",
                )
            if review_submitted:
                selected_alert = next(
                    (alert for alert in ready_alerts if alert["marché"] == review_market),
                    None,
                )
                latest_observation = next(
                    (row for row in scanner_history if row["market"] == review_market),
                    None,
                )
                if selected_alert is None or latest_observation is None:
                    st.error("Alerte invalide ou introuvable.", icon=":material/error:")
                else:
                    try:
                        fresh_snapshot = load_market_snapshot(review_market)
                        fresh_analysis = analyse_market(fresh_snapshot)
                        review = validate_review(
                            selected_alert,
                            latest_observation,
                            fresh_analysis,
                            review_acknowledged,
                        )
                        if review["eligible"]:
                            simulate(
                                review_market,
                                fresh_analysis,
                                float(review_size),
                                fresh_snapshot["price_usd"],
                            )
                            st.success(
                                "Alerte reconfirmée et transmise au moteur paper. "
                                "La décision complète est dans le journal d’audit.",
                                icon=":material/check_circle:",
                            )
                        else:
                            st.error(review["reason"], icon=":material/block:")
                    except Exception as exc:
                        st.error(f"Revalidation impossible : {exc}", icon=":material/error:")
    else:
        st.info(
            "Aucun signal BUY ou SELL actif. Les observations WAIT ne créent pas d’alerte.",
            icon=":material/notifications_off:",
        )
    if scanner_history:
        st.subheader("Mémoire des signaux", anchor=False)
        history_frame = pd.DataFrame(scanner_history)
        history_frame["date"] = pd.to_datetime(history_frame["timestamp"], utc=True)
        trend = (
            alt.Chart(history_frame)
            .mark_line(point=True, strokeWidth=2.5)
            .encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("score:Q", title="Score", scale=alt.Scale(domain=[-100, 100])),
                color=alt.Color("market:N", title="Marché"),
                tooltip=[
                    alt.Tooltip("date:T", title="Date", format="%d/%m %H:%M"),
                    alt.Tooltip("market:N", title="Marché"),
                    alt.Tooltip("action:N", title="Signal"),
                    alt.Tooltip("score:Q", title="Score", format="+.1f"),
                    alt.Tooltip("confidence:Q", title="Confiance", format=".0%"),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(trend)
        with st.container(horizontal=True):
            st.metric("Scans mémorisés", scan_count(), border=True)
            for watched_market in TOKENS:
                confirmation = confirmations.get(watched_market)
                if confirmation:
                    st.metric(
                        watched_market,
                        confirmation["action"],
                        f"{confirmation['cycles']} confirmation(s)",
                        border=True,
                    )
        with st.expander("Voir les observations mémorisées", icon=":material/history:"):
            st.dataframe(
                history_frame,
                hide_index=True,
                column_config={
                    "id": None,
                    "cycle_id": None,
                    "timestamp": None,
                    "date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
                    "market": st.column_config.TextColumn("Marché", pinned=True),
                    "action": st.column_config.TextColumn("Signal"),
                    "score": st.column_config.NumberColumn("Score", format="%+.1f"),
                    "confidence": st.column_config.ProgressColumn(
                        "Confiance", min_value=0, max_value=1, format="percent"
                    ),
                    "priority": st.column_config.NumberColumn("Priorité", format="%.2f"),
                    "price_usd": st.column_config.NumberColumn("Prix", format="$%.6f"),
                    "change_24h": st.column_config.NumberColumn("24 h", format="%+.2f %%"),
                    "liquidity_usd": st.column_config.NumberColumn("Liquidité", format="$%.0f"),
                },
            )
        st.download_button(
            "Exporter l’historique des scans",
            data=export_history(),
            file_name="jdegen_historique_scanner.json",
            mime="application/json",
            icon=":material/download:",
        )

with portfolio_tab:
    st.subheader("Portefeuille paper trading", anchor=False)
    st.write(
        "Ce portefeuille applique uniquement les décisions approuvées à un capital virtuel persistant. "
        "Il ne possède ni adresse blockchain, ni clé privée, ni capacité de signature."
    )
    portfolio = get_portfolio()
    paper_risk = calculate_risk(portfolio)
    if st.button(
        "Actualiser les valorisations",
        icon=":material/refresh:",
        key="refresh_paper_prices",
    ):
        try:
            with st.skeleton(height=100):
                refreshed_prices = {
                    position["market"]: load_market_snapshot(position["market"])["price_usd"]
                    for position in portfolio["positions"]
                }
                update_prices(refreshed_prices)
                portfolio = get_portfolio()
                paper_risk = calculate_risk(portfolio)
            st.session_state.capital = portfolio["equity"]
            st.toast("Valorisations paper mises à jour", icon=":material/check:")
        except Exception as exc:
            st.error(f"Actualisation impossible : {exc}", icon=":material/error:")

    with st.container(horizontal=True):
        st.metric("Capital virtuel", f"${portfolio['equity']:,.2f}", border=True)
        st.metric("Cash disponible", f"${portfolio['cash']:,.2f}", border=True)
        st.metric("Exposition", f"${portfolio['exposure']:,.2f}", border=True)
        st.metric(
            "P&L latent",
            f"${portfolio['unrealized_pnl']:+,.2f}",
            border=True,
        )
        st.metric(
            "P&L réalisé",
            f"${portfolio['realized_pnl']:+,.2f}",
            border=True,
        )

    st.subheader("Moniteur de risque", anchor=False)
    with st.container(horizontal=True):
        st.metric(
            "Résultat du jour",
            f"${paper_risk['daily_change']:+,.2f}",
            f"Perte {paper_risk['daily_loss_percent']:.2%}",
            border=True,
        )
        st.metric(
            "Drawdown courant",
            f"{paper_risk['drawdown_percent']:.2%}",
            f"Pic ${paper_risk['peak_equity']:,.2f}",
            delta_color="off",
            border=True,
        )
        st.metric(
            "Exposition du capital",
            f"{paper_risk['exposure_percent']:.2%}",
            border=True,
        )
        st.metric("Coupe-circuit", paper_risk["status"], border=True)
    st.progress(
        min(paper_risk["daily_loss_percent"] / paper_risk["limit_percent"], 1.0),
        text=(
            f"Perte journalière : {paper_risk['daily_loss_percent']:.2%} "
            f"sur une limite de {paper_risk['limit_percent']:.0%}"
        ),
    )
    if paper_risk["halted"]:
        st.error(
            "Coupe-circuit actif : tout nouveau BUY est bloqué. Les SELL restent autorisés "
            "pour réduire ou fermer le risque.",
            icon=":material/emergency_home:",
        )
    elif paper_risk["status"] == "VIGILANCE":
        st.warning("Le portefeuille approche d’un seuil de risque.", icon=":material/warning:")
    else:
        st.success("Tous les seuils paper sont dans la zone normale.", icon=":material/shield:")

    if portfolio["history"]:
        st.subheader("Historique du capital paper", anchor=False)
        equity_history = pd.DataFrame(portfolio["history"])
        equity_history["date"] = pd.to_datetime(equity_history["timestamp"], utc=True)
        equity_history["capital"] = equity_history["equity"]
        st.altair_chart(capital_chart(equity_history[["date", "capital"]]))
        st.caption(
            "Un point est conservé après chaque ordre simulé et chaque actualisation des prix."
        )

    if portfolio["positions"]:
        st.subheader("Positions ouvertes", anchor=False)
        positions_frame = pd.DataFrame(portfolio["positions"])
        st.dataframe(
            positions_frame,
            hide_index=True,
            column_config={
                "market": st.column_config.TextColumn("Marché", pinned=True),
                "quantity": st.column_config.NumberColumn("Quantité", format="%.8f"),
                "average_price": st.column_config.NumberColumn("Prix moyen", format="$%.6f"),
                "last_price": st.column_config.NumberColumn("Dernier prix", format="$%.6f"),
                "stop_loss_price": st.column_config.NumberColumn("Stop −5 %", format="$%.6f"),
                "take_profit_price": st.column_config.NumberColumn("Objectif +10 %", format="$%.6f"),
                "valeur_usd": st.column_config.NumberColumn("Valeur", format="$%.2f"),
                "pnl_latent_usd": st.column_config.NumberColumn("P&L latent", format="$%.2f"),
                "protection": st.column_config.TextColumn("Protection"),
                "opened_at": st.column_config.DatetimeColumn("Ouverte le", format="DD/MM/YYYY HH:mm"),
            },
        )
        protection_alerts = [
            position
            for position in portfolio["positions"]
            if position["protection"] != "DANS LES LIMITES"
        ]
        for position in protection_alerts:
            st.warning(
                f"{position['market']} • {position['protection']} au prix observé "
                f"${position['last_price']:,.6f}. Aucune fermeture automatique.",
                icon=":material/notification_important:",
            )

        st.subheader("Clôture manuelle auditée", anchor=False)
        with st.form("manual_paper_close", border=True):
            close_market = st.selectbox(
                "Position à fermer",
                [position["market"] for position in portfolio["positions"]],
            )
            close_reason = st.selectbox(
                "Motif",
                ["Décision humaine", "Stop de protection", "Objectif atteint", "Réduction du risque"],
            )
            close_confirmed = st.checkbox(
                "Je confirme la fermeture complète de cette position virtuelle."
            )
            close_submitted = st.form_submit_button(
                "Actualiser le prix et fermer",
                icon=":material/close:",
            )
        if close_submitted:
            allowed_markets = {position["market"] for position in get_portfolio()["positions"]}
            if not close_confirmed:
                st.error("Confirmation humaine obligatoire.", icon=":material/block:")
            elif close_market not in allowed_markets:
                st.error("Cette position n’est plus ouverte.", icon=":material/error:")
            else:
                try:
                    close_snapshot = load_market_snapshot(close_market)
                    persist_decision(
                        {
                            "heure": datetime.now(UTC).strftime("%H:%M:%S UTC"),
                            "marché": close_market,
                            "action": "SELL",
                            "confiance": 1.0,
                            "score": 0,
                            "prix_usd": close_snapshot["price_usd"],
                            "statut": "APPROUVÉ",
                            "position_usd": 0.0,
                            "raison": f"Clôture paper manuelle : {close_reason}",
                            "origine": "VALIDATION_HUMAINE",
                        }
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Clôture impossible : {exc}", icon=":material/error:")
    else:
        st.info(
            "Aucune position ouverte. Un signal BUY doit d’abord franchir tous les garde-fous.",
            icon=":material/account_balance_wallet:",
        )

    st.subheader("Mouvements simulés", anchor=False)
    if portfolio["trades"]:
        trades_frame = pd.DataFrame(portfolio["trades"])
        st.dataframe(
            trades_frame,
            hide_index=True,
            column_config={
                "id": None,
                "timestamp": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
                "market": st.column_config.TextColumn("Marché"),
                "side": st.column_config.TextColumn("Sens"),
                "quantity": st.column_config.NumberColumn("Quantité", format="%.8f"),
                "price": st.column_config.NumberColumn("Prix", format="$%.6f"),
                "observed_price": st.column_config.NumberColumn("Prix observé", format="$%.6f"),
                "notional": st.column_config.NumberColumn("Montant", format="$%.2f"),
                "fees": st.column_config.NumberColumn("Frais", format="$%.4f"),
                "slippage": st.column_config.NumberColumn("Slippage", format="$%.4f"),
                "realized_pnl": st.column_config.NumberColumn("P&L réalisé", format="$%.2f"),
            },
        )
    else:
        st.caption("Aucun mouvement paper enregistré.")
    st.caption("Hypothèses par ordre : 0,30 % de frais et 0,20 % de slippage.")

with performance_tab:
    st.subheader("Performance du portefeuille paper", anchor=False)
    st.caption(
        "Source : data/portfolio.db • capital initial 10 000 $ • frais et slippage inclus • "
        "données distinctes des backtests."
    )
    performance_portfolio = get_portfolio()
    performance = calculate_performance(performance_portfolio)
    with st.container(horizontal=True):
        st.metric(
            "Rendement net",
            f"{performance['net_return_percent']:+.3%}",
            f"Capital ${performance['equity']:,.2f}",
            border=True,
        )
        st.metric("Ordres paper", performance["orders"], border=True)
        st.metric("Trades clôturés", performance["closed_trades"], border=True)
        st.metric(
            "Taux de réussite",
            f"{performance['win_rate']:.1%}" if performance["win_rate"] is not None else "N/D",
            border=True,
        )
        st.metric(
            "Profit factor",
            f"{performance['profit_factor']:.2f}"
            if performance["profit_factor"] is not None
            else "N/D",
            border=True,
        )
        st.metric(
            "Drawdown maximal",
            f"{performance['max_drawdown_percent']:.3%}",
            border=True,
        )

    sample_color = (
        "green" if performance["sample_status"] == "EXPLOITABLE"
        else "orange" if performance["sample_status"] == "LIMITÉ"
        else "red"
    )
    st.badge(
        f"Échantillon {performance['sample_status'].lower()}",
        icon=":material/data_check:",
        color=sample_color,
    )
    if performance["sample_status"] == "INSUFFISANT":
        st.warning(
            "Moins de 10 trades sont clôturés : les statistiques de réussite et de rentabilité "
            "ne permettent aucune conclusion.",
            icon=":material/warning:",
        )

    if performance_portfolio["history"]:
        performance_history = pd.DataFrame(performance_portfolio["history"])
        performance_history["date"] = pd.to_datetime(performance_history["timestamp"], utc=True)
        performance_history["capital"] = performance_history["equity"]
        st.subheader("Évolution nette du capital", anchor=False)
        st.altair_chart(capital_chart(performance_history[["date", "capital"]]))

    with st.container(horizontal=True):
        st.metric("Frais cumulés", f"${performance['total_fees_usd']:,.4f}", border=True)
        st.metric(
            "Impact du slippage",
            f"${performance['total_slippage_usd']:,.4f}",
            border=True,
        )
        st.metric("Gains clôturés", f"${performance['gross_profit_usd']:,.2f}", border=True)
        st.metric("Pertes clôturées", f"${performance['gross_loss_usd']:,.2f}", border=True)
        st.metric(
            "Espérance par clôture",
            f"${performance['expectancy_usd']:+,.2f}"
            if performance["expectancy_usd"] is not None
            else "N/D",
            border=True,
        )

    if performance["by_market"]:
        st.subheader("Attribution par marché", anchor=False)
        attribution = pd.DataFrame(performance["by_market"])
        st.bar_chart(attribution, x="marché", y="volume_usd")
        st.dataframe(
            attribution,
            hide_index=True,
            column_config={
                "marché": st.column_config.TextColumn("Marché", pinned=True),
                "ordres": st.column_config.NumberColumn("Ordres"),
                "achats": st.column_config.NumberColumn("Achats"),
                "ventes": st.column_config.NumberColumn("Ventes"),
                "volume_usd": st.column_config.NumberColumn("Volume simulé", format="$%.2f"),
                "frais_usd": st.column_config.NumberColumn("Frais", format="$%.4f"),
                "slippage_usd": st.column_config.NumberColumn("Slippage", format="$%.4f"),
                "pnl_réalisé_usd": st.column_config.NumberColumn("P&L réalisé", format="$%.2f"),
            },
        )
    else:
        st.info("Aucun ordre paper à analyser.", icon=":material/analytics:")

    with st.expander("Définitions des métriques", icon=":material/info:"):
        st.write(
            "**Rendement net** = capital paper courant / 10 000 $ − 1.  "
            "\n**Taux de réussite** = ventes gagnantes / ventes clôturées.  "
            "\n**Profit factor** = gains clôturés / pertes clôturées ; indisponible sans perte.  "
            "\n**Drawdown maximal** = plus forte baisse depuis un sommet de la courbe persistante."
        )

with backtest_tab:
    st.subheader("Tester avant de risquer", anchor=False)
    st.write(
        "Ce test applique un croisement de moyennes mobiles sur des bougies réelles de quatre heures. "
        "Il utilise 2 % du capital par position et inclut 0,30 % de frais plus 0,20 % de slippage par ordre."
    )
    with st.form("backtest_controls", border=True):
        backtest_market = st.selectbox("Marché historique", list(TOKENS), key="backtest_market")
        candle_count = st.segmented_control(
            "Profondeur historique",
            options=[180, 300, 600, 1_000],
            default=600,
            format_func=lambda value: f"{value} bougies · ~{value / 6:.0f} jours",
            help="Le fournisseur peut retourner moins de bougies que demandé selon l’âge du pool.",
        )
        windows = st.columns(2)
        short_window = windows[0].number_input("Moyenne courte", 3, 20, 5)
        long_window = windows[1].number_input("Moyenne longue", 8, 40, 12)
        run_test = st.form_submit_button(
            "Lancer le backtest",
            icon=":material/history:",
            type="primary",
            width="stretch",
        )

    if run_test:
        try:
            with st.skeleton(height=300):
                selected_pair = load_market_snapshot(backtest_market)
                candles = load_ohlcv(selected_pair["pair_address"], candle_count)
                data_quality = assess_ohlcv_quality(candles)
                result = run_backtest(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                trade_bootstrap = bootstrap_trade_outcomes(result["trades"])
                market_regimes = (
                    analyze_market_regimes(
                        candles,
                        short_window=int(short_window),
                        long_window=int(long_window),
                    )
                    if len(candles) >= 3 * (int(long_window) + 2)
                    else None
                )
                comparison = compare_strategies(
                    candles,
                    custom_short=int(short_window),
                    custom_long=int(long_window),
                )
                validation = validate_out_of_sample(candles)
                walk_forward = validate_walk_forward(candles) if len(candles) >= 120 else None
                sensitivity = analyze_parameter_sensitivity(
                    candles,
                    selected_short=int(short_window),
                    selected_long=int(long_window),
                )
                execution_stress = stress_execution_costs(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                confirmation_lab = compare_signal_confirmations(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                strength_lab = compare_signal_strength_filters(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                volume_lab = compare_volume_filters(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                volume_validation = validate_volume_filter_out_of_sample(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                volume_walk_forward = (
                    validate_volume_filter_walk_forward(
                        candles, short_window=int(short_window), long_window=int(long_window)
                    ) if len(candles) // 6 >= max(int(long_window) + 2, 20) else None
                )
                strength_validation = validate_strength_filter_out_of_sample(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                strength_walk_forward = (
                    validate_strength_filter_walk_forward(
                        candles,
                        short_window=int(short_window),
                        long_window=int(long_window),
                    )
                    if len(candles) // 6 >= int(long_window) + 2
                    else None
                )
                confirmation_validation = validate_confirmation_out_of_sample(
                    candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                )
                confirmation_walk_forward = (
                    validate_confirmation_walk_forward(
                        candles,
                        short_window=int(short_window),
                        long_window=int(long_window),
                    )
                    if len(candles) // 6 >= int(long_window) + 2
                    else None
                )
                readiness = summarize_validation_readiness(
                    result,
                    data_quality,
                    trade_bootstrap,
                    market_regimes,
                    validation,
                    walk_forward,
                    sensitivity,
                    execution_stress,
                    confirmation_walk_forward,
                    strength_walk_forward,
                    volume_walk_forward,
                )
                cross_market = run_cross_market_validation(300)
                candidate = select_candidate(cross_market, readiness)
                paper_policy = build_supervised_paper_policy(candidate)
                paper_performance = calculate_performance(get_portfolio())
                paper_drift = assess_paper_drift(
                    paper_return=paper_performance["net_return_percent"] * 100,
                    backtest_return=result["return_percent"],
                    paper_drawdown=paper_performance["max_drawdown_percent"] * 100,
                    backtest_drawdown=result["max_drawdown_percent"],
                    closed_trades=paper_performance["closed_trades"],
                )
                report = build_backtest_report(
                    market=backtest_market,
                    candles=candles,
                    short_window=int(short_window),
                    long_window=int(long_window),
                    result=result,
                    data_quality=data_quality,
                    trade_bootstrap=trade_bootstrap,
                    market_regimes=market_regimes,
                    out_of_sample=validation,
                    walk_forward=walk_forward,
                    sensitivity=sensitivity,
                    execution_stress=execution_stress,
                    confirmation_lab=confirmation_lab,
                    strength_lab=strength_lab,
                    volume_lab=volume_lab,
                    volume_validation=volume_validation,
                    volume_walk_forward=volume_walk_forward,
                    strength_validation=strength_validation,
                    strength_walk_forward=strength_walk_forward,
                    confirmation_validation=confirmation_validation,
                    confirmation_walk_forward=confirmation_walk_forward,
                    readiness=readiness,
                )
                archive_result = archive_backtest_report(report)
            st.session_state["backtest_result"] = result
            st.session_state["trade_bootstrap"] = trade_bootstrap
            st.session_state["market_regimes"] = market_regimes
            st.session_state["ohlcv_quality"] = data_quality
            st.session_state["requested_candle_count"] = int(candle_count)
            st.session_state["backtest_comparison"] = comparison
            st.session_state["out_of_sample"] = validation
            st.session_state["walk_forward"] = walk_forward
            st.session_state["parameter_sensitivity"] = sensitivity
            st.session_state["execution_stress"] = execution_stress
            st.session_state["confirmation_lab"] = confirmation_lab
            st.session_state["strength_lab"] = strength_lab
            st.session_state["volume_lab"] = volume_lab
            st.session_state["volume_validation"] = volume_validation
            st.session_state["volume_walk_forward"] = volume_walk_forward
            st.session_state["strength_validation"] = strength_validation
            st.session_state["strength_walk_forward"] = strength_walk_forward
            st.session_state["confirmation_validation"] = confirmation_validation
            st.session_state["confirmation_walk_forward"] = confirmation_walk_forward
            st.session_state["validation_readiness"] = readiness
            st.session_state["cross_market_validation"] = cross_market
            st.session_state["strategy_candidate"] = candidate
            st.session_state["paper_policy"] = paper_policy
            st.session_state["paper_drift"] = paper_drift
            st.session_state["backtest_report"] = report
            st.session_state["backtest_archive_result"] = archive_result
            st.session_state["backtest_label"] = backtest_market
        except Exception as exc:
            st.error(f"Backtest impossible : {exc}", icon=":material/error:")

    result = st.session_state.get("backtest_result")
    if result:
        st.markdown(f":green-badge[Données OHLCV réelles] :blue-badge[{st.session_state['backtest_label']}]")
        with st.container(horizontal=True):
            st.metric("Capital final", f"${result['final_capital']:,.2f}", border=True)
            st.metric("Rendement simulé", f"{result['return_percent']:+.3f} %", border=True)
            st.metric("Drawdown maximal", f"{result['max_drawdown_percent']:.3f} %", border=True)
            st.metric("Trades clôturés", result["round_trips"], border=True)
            st.metric("Taux de réussite", f"{result['win_rate_percent']:.1f} %", border=True)

        data_quality = st.session_state.get("ohlcv_quality")
        if data_quality:
            st.subheader("Qualité des données OHLCV", anchor=False)
            with st.container(horizontal=True):
                st.metric(
                    "Contrôles de données",
                    f"{data_quality['passed']} / {data_quality['total']}",
                    border=True,
                )
                st.metric(
                    "Bougies analysées",
                    data_quality["row_count"],
                    f"{st.session_state.get('requested_candle_count', data_quality['row_count'])} demandées",
                    border=True,
                )
                st.metric(
                    "Couverture réelle",
                    f"{data_quality['coverage_days']:.1f} jours",
                    border=True,
                )
                st.metric(
                    "Intervalle observé",
                    f"{data_quality['expected_interval_hours']:.1f} h",
                    border=True,
                )
                st.metric(
                    "Retard de la dernière bougie",
                    f"{data_quality['freshness_hours']:.1f} h",
                    border=True,
                )
            quality_color = "green" if data_quality["passes"] else "red"
            quality_label = (
                "Données aptes au Backtest"
                if data_quality["passes"]
                else "Données à risque"
            )
            st.badge(
                quality_label,
                icon=":material/database_search:",
                color=quality_color,
            )
            st.dataframe(
                pd.DataFrame(data_quality["checks"]),
                hide_index=True,
                column_config={
                    "contrôle": st.column_config.TextColumn("Contrôle", pinned=True),
                    "réussi": st.column_config.CheckboxColumn("Réussi"),
                    "preuve": st.column_config.TextColumn("Preuve observée"),
                },
            )
            st.caption(
                "Un échec de qualité abaisse le verdict global. Le Backtest reste affiché pour "
                "diagnostic, mais ses conclusions ne doivent pas être utilisées."
            )

        st.subheader("Performance ajustée au risque", anchor=False)
        sharpe_value = result.get("sharpe_ratio")
        sortino_value = result.get("sortino_ratio")
        profit_factor_value = result.get("profit_factor")
        expectancy_value = result.get("expectancy_per_trade")
        with st.container(horizontal=True):
            st.metric(
                "Ratio de Sharpe",
                f"{sharpe_value:.3f}" if sharpe_value is not None else "N/D",
                border=True,
            )
            st.metric(
                "Ratio de Sortino",
                f"{sortino_value:.3f}" if sortino_value is not None else "N/D",
                border=True,
            )
            st.metric(
                "Facteur de profit",
                f"{profit_factor_value:.3f}" if profit_factor_value is not None else "N/D",
                border=True,
            )
            st.metric(
                "Espérance par trade",
                f"${expectancy_value:+.2f}" if expectancy_value is not None else "N/D",
                border=True,
            )
            st.metric(
                "Temps exposé au marché",
                f"{result['exposure_percent']:.1f} %",
                border=True,
            )
        st.caption(
            "Sharpe et Sortino sont calculés sur les variations du capital par bougie de 4 h "
            "et annualisés sur 2 190 périodes. N/D signifie que la variance ou l’échantillon "
            "de trades est insuffisant pour produire un ratio défendable."
        )

        trade_bootstrap = st.session_state.get("trade_bootstrap")
        if trade_bootstrap and trade_bootstrap["trade_count"] > 0:
            st.subheader("Incertitude statistique des trades", anchor=False)
            with st.container(horizontal=True):
                st.metric(
                    "Trades observés",
                    trade_bootstrap["trade_count"],
                    border=True,
                )
                st.metric(
                    "Probabilité simulée d’un P&L positif",
                    f"{trade_bootstrap['probability_positive_percent']:.1f} %",
                    border=True,
                )
                st.metric(
                    "Scénario prudent — 5e percentile",
                    f"${trade_bootstrap['pessimistic_pnl']:+.2f}",
                    border=True,
                )
                st.metric(
                    "Scénario médian",
                    f"${trade_bootstrap['median_pnl']:+.2f}",
                    border=True,
                )
                st.metric(
                    "Scénario favorable — 95e percentile",
                    f"${trade_bootstrap['optimistic_pnl']:+.2f}",
                    border=True,
                )
            if trade_bootstrap["sufficient_sample"]:
                st.badge(
                    "Échantillon minimal atteint",
                    icon=":material/scatter_plot:",
                    color="green",
                )
            else:
                st.warning(
                    "Moins de 10 trades clôturés : la distribution est exploratoire et ne doit "
                    "pas être interprétée comme une confiance statistique établie.",
                    icon=":material/science:",
                )
            bootstrap_frame = pd.DataFrame(
                {"P&L total simulé": trade_bootstrap["simulated_totals"]}
            )
            bootstrap_histogram = (
                alt.Chart(bootstrap_frame)
                .mark_bar(color="#38bdf8")
                .encode(
                    x=alt.X(
                        "P&L total simulé:Q",
                        bin=alt.Bin(maxbins=30),
                        title="P&L total rééchantillonné ($)",
                    ),
                    y=alt.Y("count():Q", title="Nombre de simulations"),
                    tooltip=[alt.Tooltip("count():Q", title="Simulations")],
                )
                .properties(height=280)
            )
            zero_bootstrap = alt.Chart(pd.DataFrame({"seuil": [0]})).mark_rule(
                color="#ef4444", strokeDash=[5, 5]
            ).encode(x="seuil:Q")
            st.altair_chart(bootstrap_histogram + zero_bootstrap)
            st.caption(
                "1 000 simulations avec remise, graine fixe 42, même nombre de trades que "
                "l’échantillon observé. Le bootstrap suppose que les trades historiques sont "
                "représentatifs et indépendants ; il ne prédit pas les conditions futures."
            )
        else:
            st.info(
                "Aucun trade clôturé : le bootstrap statistique n’est pas calculable.",
                icon=":material/scatter_plot:",
            )

        market_regimes = st.session_state.get("market_regimes")
        if market_regimes:
            st.subheader("Validation par régime de marché", anchor=False)
            with st.container(horizontal=True):
                st.metric(
                    "Périodes positives",
                    f"{market_regimes['positive_periods']} / 3",
                    border=True,
                )
                st.metric(
                    "Périodes au-dessus du buy & hold",
                    f"{market_regimes['outperforming_periods']} / 3",
                    border=True,
                )
                st.metric(
                    "Régimes observés",
                    str(len(market_regimes["regimes_observed"])),
                    ", ".join(market_regimes["regimes_observed"]),
                    border=True,
                )
            regime_color = "green" if market_regimes["passes"] else "orange"
            regime_label = (
                "Comportement multi-périodes satisfaisant"
                if market_regimes["passes"]
                else "Dépendance au régime à surveiller"
            )
            st.badge(
                regime_label,
                icon=":material/landscape:",
                color=regime_color,
            )
            regime_frame = pd.DataFrame(market_regimes["periods"])
            st.dataframe(
                regime_frame,
                hide_index=True,
                column_config={
                    "début": st.column_config.DatetimeColumn("Début", format="DD/MM/YYYY HH:mm"),
                    "fin": st.column_config.DatetimeColumn("Fin", format="DD/MM/YYYY HH:mm"),
                    "mouvement_marché": st.column_config.NumberColumn("Marché brut", format="%.3f %%"),
                    "rendement_stratégie": st.column_config.NumberColumn("Stratégie", format="%.3f %%"),
                    "rendement_buy_hold": st.column_config.NumberColumn("Buy & hold", format="%.3f %%"),
                    "surperformance": st.column_config.NumberColumn("Surperformance", format="%.3f %%"),
                    "drawdown": st.column_config.NumberColumn("Drawdown", format="%.3f %%"),
                    "positif": st.column_config.CheckboxColumn("Positif"),
                    "surperforme": st.column_config.CheckboxColumn("Surperforme"),
                },
            )
            regime_chart = regime_frame[["période", "rendement_stratégie", "rendement_buy_hold"]].melt(
                id_vars="période",
                var_name="série",
                value_name="rendement",
            )
            regime_chart["série"] = regime_chart["série"].replace(
                {
                    "rendement_stratégie": "Stratégie",
                    "rendement_buy_hold": "Buy & hold",
                }
            )
            st.bar_chart(
                regime_chart,
                x="période",
                y="rendement",
                color="série",
                stack=False,
            )
            st.caption(
                "Les trois périodes sont contiguës, chronologiques et sans chevauchement. Le régime "
                "décrit le mouvement brut du marché ; il n’est pas utilisé pour modifier les signaux."
            )
        else:
            st.info(
                "Historique insuffisant pour trois régimes indépendants avec cette moyenne longue.",
                icon=":material/landscape:",
            )

        price_history = pd.DataFrame(result["candles"])
        st.subheader("Bougies et moyennes mobiles", anchor=False)
        st.altair_chart(candlestick_chart(price_history))
        st.caption(
            "Vert : clôture ≥ ouverture • rouge : clôture < ouverture • "
            "bleu : moyenne courte • orange : moyenne longue."
        )

        equity = pd.DataFrame(result["equity"])
        st.subheader("Courbe du capital", anchor=False)
        st.altair_chart(capital_chart(equity))
        st.caption(
            f"Échelle resserrée : de ${equity['capital'].min():,.2f} "
            f"à ${equity['capital'].max():,.2f}."
        )

        with st.expander("Voir les opérations simulées", icon=":material/table_chart:"):
            trades = pd.DataFrame(result["trades"])
            st.dataframe(
                trades,
                hide_index=True,
                column_config={
                    "date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
                    "prix": st.column_config.NumberColumn("Prix exécuté", format="$%.6f"),
                    "pnl": st.column_config.NumberColumn("P&L", format="$%.2f"),
                },
            )
        st.caption("Source historique : GeckoTerminal Public API • résultats hypothétiques, non prédictifs.")

        comparison = st.session_state.get("backtest_comparison")
        if comparison:
            st.subheader("Comparaison des variantes", anchor=False)
            st.caption(
                "Toutes les variantes utilisent les mêmes bougies, 10 000 $, une position de 2 % "
                "et les mêmes hypothèses de frais et de slippage."
            )
            comparison_frame = pd.DataFrame(comparison["summary"])
            st.dataframe(
                comparison_frame,
                hide_index=True,
                column_config={
                    "Capital final": st.column_config.NumberColumn(format="$%.2f"),
                    "Rendement": st.column_config.NumberColumn(format="percent"),
                    "Drawdown": st.column_config.NumberColumn(format="percent"),
                    "Réussite": st.column_config.NumberColumn(format="percent"),
                },
            )
            curves = pd.DataFrame(comparison["curves"])
            st.subheader("Capitaux simulés", anchor=False)
            st.altair_chart(capital_comparison_chart(curves))
            st.caption(
                f"Échelle commune resserrée : de ${curves['capital'].min():,.2f} "
                f"à ${curves['capital'].max():,.2f}."
            )
            st.warning(
                "Le meilleur résultat sur cette période n’est pas automatiquement la meilleure stratégie. "
                "Une validation hors échantillon sera nécessaire.",
                icon=":material/warning:",
            )

        sensitivity = st.session_state.get("parameter_sensitivity")
        if sensitivity:
            st.subheader("Sensibilité des paramètres", anchor=False)
            st.write(
                "Cette grille teste les réglages voisins de la configuration choisie. "
                "Une zone homogène est plus rassurante qu’un unique résultat exceptionnel."
            )
            with st.container(horizontal=True):
                st.metric(
                    "Variantes rentables",
                    f"{sensitivity['profitable_count']} / {sensitivity['combination_count']}",
                    f"{sensitivity['profitable_percent']:.1f} %",
                    border=True,
                )
                st.metric(
                    "Rendement médian",
                    f"{sensitivity['median_return']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Meilleure variante",
                    f"{sensitivity['best_return']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Pire variante",
                    f"{sensitivity['worst_return']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Dispersion",
                    f"{sensitivity['spread']:.3f} points",
                    border=True,
                )
            sensitivity_color = "green" if sensitivity["passes"] else "orange"
            sensitivity_status = (
                "Zone de paramètres cohérente"
                if sensitivity["passes"]
                else "Dépendance aux paramètres à surveiller"
            )
            st.badge(
                sensitivity_status,
                icon=":material/grid_view:",
                color=sensitivity_color,
            )
            sensitivity_frame = pd.DataFrame(sensitivity["results"])
            heatmap = (
                alt.Chart(sensitivity_frame)
                .mark_rect(cornerRadius=3)
                .encode(
                    x=alt.X("moyenne_longue:O", title="Moyenne longue"),
                    y=alt.Y("moyenne_courte:O", title="Moyenne courte"),
                    color=alt.Color(
                        "rendement:Q",
                        title="Rendement (%)",
                        scale=alt.Scale(scheme="redyellowgreen", domainMid=0),
                    ),
                    tooltip=[
                        alt.Tooltip("moyenne_courte:O", title="Moyenne courte"),
                        alt.Tooltip("moyenne_longue:O", title="Moyenne longue"),
                        alt.Tooltip("rendement:Q", title="Rendement", format="+.3f"),
                        alt.Tooltip("drawdown:Q", title="Drawdown", format=".3f"),
                        alt.Tooltip("trades:Q", title="Trades"),
                        alt.Tooltip("sélectionnée:N", title="Réglage choisi"),
                    ],
                )
                .properties(height=300)
            )
            st.altair_chart(heatmap)
            with st.expander("Voir les variantes de sensibilité", icon=":material/table_chart:"):
                st.dataframe(
                    sensitivity_frame,
                    hide_index=True,
                    column_config={
                        "moyenne_courte": st.column_config.NumberColumn("Moyenne courte"),
                        "moyenne_longue": st.column_config.NumberColumn("Moyenne longue"),
                        "rendement": st.column_config.NumberColumn("Rendement", format="%.3f %%"),
                        "drawdown": st.column_config.NumberColumn("Drawdown", format="%.3f %%"),
                        "sélectionnée": st.column_config.CheckboxColumn("Réglage choisi"),
                    },
                )
            st.caption(
                "Le verdict exige un réglage choisi positif, une médiane positive et au moins "
                "60 % de variantes voisines rentables. Ce diagnostic reste historique et non prédictif."
            )

        execution_stress = st.session_state.get("execution_stress")
        if execution_stress:
            st.subheader("Stress test des coûts d’exécution", anchor=False)
            st.write(
                "La stratégie est rejouée sans changer ses signaux, avec des frais et un slippage "
                "croissants. Cela mesure la part du résultat qui dépend d’une exécution favorable."
            )
            with st.container(horizontal=True):
                st.metric(
                    "Scénarios rentables",
                    f"{execution_stress['profitable_scenarios']} / {execution_stress['scenario_count']}",
                    border=True,
                )
                st.metric(
                    "Rendement normal",
                    f"{execution_stress['baseline_return']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Rendement extrême",
                    f"{execution_stress['extreme_return']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Érosion liée aux coûts",
                    f"-{execution_stress['cost_erosion']:.3f} point",
                    border=True,
                )
            stress_color = "green" if execution_stress["passes"] else "red"
            stress_status = (
                "Résiste aux trois scénarios"
                if execution_stress["passes"]
                else "Rentabilité sensible aux coûts"
            )
            st.badge(
                stress_status,
                icon=":material/speed:",
                color=stress_color,
            )
            stress_frame = pd.DataFrame(execution_stress["scenarios"])
            stress_chart = (
                alt.Chart(stress_frame)
                .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                .encode(
                    x=alt.X("scénario:N", title=None, sort=None),
                    y=alt.Y("rendement:Q", title="Rendement (%)"),
                    color=alt.condition(
                        "datum.rendement >= 0",
                        alt.value("#22c55e"),
                        alt.value("#ef4444"),
                    ),
                    tooltip=[
                        alt.Tooltip("scénario:N", title="Scénario"),
                        alt.Tooltip("frais:Q", title="Frais (%)", format=".2f"),
                        alt.Tooltip("slippage:Q", title="Slippage (%)", format=".2f"),
                        alt.Tooltip("rendement:Q", title="Rendement (%)", format="+.3f"),
                    ],
                )
                .properties(height=280)
            )
            zero_line = alt.Chart(pd.DataFrame({"seuil": [0]})).mark_rule(
                color="#94a3b8", strokeDash=[5, 5]
            ).encode(y="seuil:Q")
            st.altair_chart(stress_chart + zero_line)
            st.dataframe(
                stress_frame,
                hide_index=True,
                column_config={
                    "frais": st.column_config.NumberColumn("Frais", format="%.2f %%"),
                    "slippage": st.column_config.NumberColumn("Slippage", format="%.2f %%"),
                    "coût_total_par_exécution": st.column_config.NumberColumn(
                        "Coût total/exécution", format="%.2f %%"
                    ),
                    "rendement": st.column_config.NumberColumn("Rendement", format="%.3f %%"),
                    "capital_final": st.column_config.NumberColumn("Capital final", format="$%.2f"),
                    "drawdown": st.column_config.NumberColumn("Drawdown", format="%.3f %%"),
                    "rentable": st.column_config.CheckboxColumn("Rentable"),
                },
            )
            st.caption(
                "Les coûts sont appliqués à chaque achat et à chaque vente. Les scénarios ne "
                "modélisent pas les interruptions réseau, le MEV ni une liquidité totalement absente."
            )

        volume_lab = st.session_state.get("volume_lab")
        if volume_lab:
            st.subheader("Laboratoire de participation du marché", anchor=False)
            st.write(
                "Les achats peuvent exiger un volume égal ou supérieur à la médiane des "
                "20 dernières bougies. Les ventes restent toujours autorisées."
            )
            lowest_volume = volume_lab["lowest_turnover"]
            stressed_volume = volume_lab["best_stressed"]
            with st.container(horizontal=True):
                st.metric("Trades sans filtre volume", volume_lab["baseline_trades"], border=True)
                st.metric(
                    "Rotation minimale par volume",
                    lowest_volume["libellé"],
                    f"{lowest_volume['trades']} trades",
                    border=True,
                )
                st.metric(
                    "Meilleur volume sous stress",
                    stressed_volume["libellé"],
                    f"{stressed_volume['rendement_stress']:+.3f} %",
                    border=True,
                )
            st.badge(
                "Filtre indépendant en recherche — sorties jamais bloquées",
                icon=":material/bar_chart:",
                color="blue",
            )
            volume_frame = pd.DataFrame(volume_lab["variants"])
            volume_chart_frame = volume_frame.melt(
                id_vars="libellé",
                value_vars=["rendement_normal", "rendement_stress"],
                var_name="conditions",
                value_name="rendement",
            )
            volume_chart = (
                alt.Chart(volume_chart_frame)
                .mark_bar()
                .encode(
                    x=alt.X("libellé:N", title="Filtre de volume", sort=None),
                    y=alt.Y("rendement:Q", title="Rendement (%)"),
                    xOffset="conditions:N",
                    color=alt.Color(
                        "conditions:N",
                        title="Conditions",
                        scale=alt.Scale(
                            domain=["rendement_normal", "rendement_stress"],
                            range=["#8b5cf6", "#f97316"],
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("libellé:N", title="Filtre"),
                        alt.Tooltip("conditions:N", title="Conditions"),
                        alt.Tooltip("rendement:Q", title="Rendement (%)", format="+.3f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(volume_chart)
            st.dataframe(
                volume_frame,
                hide_index=True,
                column_config={
                    "ratio": None,
                    "libellé": st.column_config.TextColumn("Filtre de volume", pinned=True),
                    "rendement_normal": st.column_config.NumberColumn("Rendement normal", format="%.3f %%"),
                    "rendement_stress": st.column_config.NumberColumn("Rendement stressé", format="%.3f %%"),
                    "érosion_coûts": st.column_config.NumberColumn("Érosion coûts", format="%.3f point"),
                    "drawdown": st.column_config.NumberColumn("Drawdown", format="%.3f %%"),
                    "facteur_profit": st.column_config.NumberColumn("Facteur profit", format="%.3f"),
                    "espérance": st.column_config.NumberColumn("Espérance", format="$%.2f"),
                },
            )
            st.caption(
                "Le volume est une information indépendante du croisement des moyennes, mais sa "
                "médiane historique reste non prédictive. Une validation future sera nécessaire."
            )
            volume_validation = st.session_state.get("volume_validation")
            if volume_validation:
                st.markdown("#### Test futur séparé du volume")
                st.write(
                    f"Le filtre est choisi sous coûts extrêmes sur les "
                    f"**{volume_validation['train_count']} premières bougies**, puis figé sur les "
                    f"**{volume_validation['test_count']} suivantes**."
                )
                with st.container(horizontal=True):
                    st.metric(
                        "Volume choisi sur entraînement",
                        volume_validation["selected_label"],
                        f"{volume_validation['training_stressed_return']:+.3f} % stressé",
                        border=True,
                    )
                    st.metric(
                        "Volume sur période future",
                        f"{volume_validation['test_stressed_return']:+.3f} %",
                        border=True,
                    )
                    st.metric(
                        "Écart futur sans volume",
                        f"{volume_validation['excess_return_percent']:+.3f} point",
                        border=True,
                    )
                    st.metric(
                        "Trades futurs du volume",
                        volume_validation["test_trades"],
                        border=True,
                    )
                volume_validation_color = "green" if volume_validation["passes"] else "red"
                volume_validation_text = (
                    "Filtre de volume validé hors échantillon"
                    if volume_validation["passes"]
                    else "Filtre de volume non validé hors échantillon"
                )
                st.badge(
                    volume_validation_text,
                    icon=":material/query_stats:",
                    color=volume_validation_color,
                )
                st.dataframe(
                    pd.DataFrame(volume_validation["training_results"]),
                    hide_index=True,
                    column_config={
                        "ratio": None,
                        "libellé": st.column_config.TextColumn("Filtre de volume", pinned=True),
                        "rendement_stress": st.column_config.NumberColumn(
                            "Entraînement stressé", format="%.3f %%"
                        ),
                    },
                )
                st.caption(
                    f"Coupure chronologique : {volume_validation['split_date']:%d/%m/%Y %H:%M} UTC. "
                    "Le futur ne participe ni au choix du ratio ni au calcul de la médiane passée."
                )
            volume_walk = st.session_state.get("volume_walk_forward")
            if volume_walk:
                st.markdown("#### Walk-forward du volume")
                with st.container(horizontal=True):
                    st.metric("Plis volume positifs", f"{volume_walk['positive_folds']} / {volume_walk['fold_count']}", border=True)
                    st.metric("Plis volume surperformants", f"{volume_walk['outperforming_folds']} / {volume_walk['fold_count']}", border=True)
                    st.metric("Rendement volume moyen", f"{volume_walk['average_test_return']:+.3f} %", border=True)
                    st.metric("Avantage volume moyen", f"{volume_walk['average_excess_return']:+.3f} point", border=True)
                st.badge(
                    "Walk-forward volume validé" if volume_walk["passes"] else "Walk-forward volume non validé",
                    icon=":material/timeline:", color="green" if volume_walk["passes"] else "red",
                )
                st.dataframe(
                    pd.DataFrame(volume_walk["folds"]), hide_index=True,
                    column_config={"ratio": None, "libellé": st.column_config.TextColumn("Filtre choisi", pinned=True),
                                   "rendement_test_stressé": st.column_config.NumberColumn("Rendement stressé", format="%.3f %%"),
                                   "écart_vs_sans_filtre": st.column_config.NumberColumn("Écart", format="%+.3f point"),
                                   "positif": st.column_config.CheckboxColumn("Positif"),
                                   "surperforme": st.column_config.CheckboxColumn("Surperforme")},
                )

        strength_lab = st.session_state.get("strength_lab")
        if strength_lab:
            st.subheader("Laboratoire de force du signal", anchor=False)
            st.write(
                "Jarvis exige un écart minimal entre la moyenne courte et la moyenne longue. "
                "La zone neutre conserve la position existante et évite certains allers-retours."
            )
            lowest_strength = strength_lab["lowest_turnover"]
            stressed_strength = strength_lab["best_stressed"]
            with st.container(horizontal=True):
                st.metric(
                    "Trades sans filtre",
                    strength_lab["baseline_trades"],
                    border=True,
                )
                st.metric(
                    "Rotation minimale du filtre",
                    lowest_strength["libellé"],
                    f"{lowest_strength['trades']} trades",
                    border=True,
                )
                st.metric(
                    "Meilleur filtre sous stress",
                    stressed_strength["libellé"],
                    f"{stressed_strength['rendement_stress']:+.3f} %",
                    border=True,
                )
            st.badge(
                "Recherche uniquement — stratégie active inchangée",
                icon=":material/filter_alt:",
                color="blue",
            )
            strength_frame = pd.DataFrame(strength_lab["variants"])
            strength_chart_frame = strength_frame.melt(
                id_vars="libellé",
                value_vars=["rendement_normal", "rendement_stress"],
                var_name="conditions",
                value_name="rendement",
            )
            strength_chart = (
                alt.Chart(strength_chart_frame)
                .mark_bar()
                .encode(
                    x=alt.X("libellé:N", title="Filtre", sort=None),
                    y=alt.Y("rendement:Q", title="Rendement (%)"),
                    xOffset="conditions:N",
                    color=alt.Color(
                        "conditions:N",
                        title="Conditions",
                        scale=alt.Scale(
                            domain=["rendement_normal", "rendement_stress"],
                            range=["#3b82f6", "#f97316"],
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("libellé:N", title="Filtre"),
                        alt.Tooltip("conditions:N", title="Conditions"),
                        alt.Tooltip("rendement:Q", title="Rendement (%)", format="+.3f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(strength_chart)
            st.dataframe(
                strength_frame,
                hide_index=True,
                column_config={
                    "seuil": None,
                    "libellé": st.column_config.TextColumn("Filtre", pinned=True),
                    "rendement_normal": st.column_config.NumberColumn(
                        "Rendement normal", format="%.3f %%"
                    ),
                    "rendement_stress": st.column_config.NumberColumn(
                        "Rendement stressé", format="%.3f %%"
                    ),
                    "érosion_coûts": st.column_config.NumberColumn(
                        "Érosion coûts", format="%.3f point"
                    ),
                    "drawdown": st.column_config.NumberColumn("Drawdown", format="%.3f %%"),
                    "facteur_profit": st.column_config.NumberColumn(
                        "Facteur profit", format="%.3f"
                    ),
                    "espérance": st.column_config.NumberColumn("Espérance", format="$%.2f"),
                },
            )
            st.caption(
                "Un seuil peut réduire le bruit mais retarder les retournements. Aucun seuil "
                "n’est retenu avant une validation chronologique séparée."
            )
            strength_validation = st.session_state.get("strength_validation")
            if strength_validation:
                st.markdown("#### Test futur séparé du filtre")
                st.write(
                    f"Le seuil est choisi sous coûts extrêmes sur les "
                    f"**{strength_validation['train_count']} premières bougies**, puis testé sans "
                    f"modification sur les **{strength_validation['test_count']} suivantes**."
                )
                with st.container(horizontal=True):
                    st.metric(
                        "Filtre choisi sur entraînement",
                        strength_validation["selected_label"],
                        f"{strength_validation['training_stressed_return']:+.3f} % stressé",
                        border=True,
                    )
                    st.metric(
                        "Filtre sur période future",
                        f"{strength_validation['test_stressed_return']:+.3f} %",
                        border=True,
                    )
                    st.metric(
                        "Écart futur sans filtre",
                        f"{strength_validation['excess_return_percent']:+.3f} point",
                        border=True,
                    )
                    st.metric(
                        "Trades futurs du filtre",
                        strength_validation["test_trades"],
                        border=True,
                    )
                strength_validation_color = (
                    "green" if strength_validation["passes"] else "red"
                )
                strength_validation_text = (
                    "Filtre de force validé hors échantillon"
                    if strength_validation["passes"]
                    else "Filtre de force non validé hors échantillon"
                )
                st.badge(
                    strength_validation_text,
                    icon=":material/filter_alt_off:",
                    color=strength_validation_color,
                )
                st.dataframe(
                    pd.DataFrame(strength_validation["training_results"]),
                    hide_index=True,
                    column_config={
                        "seuil": None,
                        "libellé": st.column_config.TextColumn("Filtre", pinned=True),
                        "rendement_stress": st.column_config.NumberColumn(
                            "Entraînement stressé", format="%.3f %%"
                        ),
                    },
                )
                st.caption(
                    f"Coupure chronologique : {strength_validation['split_date']:%d/%m/%Y %H:%M} UTC. "
                    "La période future ne participe jamais au choix du seuil."
                )
            strength_walk = st.session_state.get("strength_walk_forward")
            if strength_walk:
                st.markdown("#### Walk-forward du filtre de force")
                st.write(
                    "Le seuil est resélectionné avant chaque pli, puis testé sous coûts extrêmes "
                    "sur une fenêtre future qui n’a pas participé au choix."
                )
                with st.container(horizontal=True):
                    st.metric(
                        "Plis positifs du filtre",
                        f"{strength_walk['positive_folds']} / {strength_walk['fold_count']}",
                        border=True,
                    )
                    st.metric(
                        "Plis meilleurs que sans filtre",
                        f"{strength_walk['outperforming_folds']} / {strength_walk['fold_count']}",
                        border=True,
                    )
                    st.metric(
                        "Rendement moyen du filtre",
                        f"{strength_walk['average_test_return']:+.3f} %",
                        border=True,
                    )
                    st.metric(
                        "Avantage moyen du filtre",
                        f"{strength_walk['average_excess_return']:+.3f} point",
                        border=True,
                    )
                strength_walk_color = "green" if strength_walk["passes"] else "red"
                strength_walk_text = (
                    "Walk-forward du filtre validé"
                    if strength_walk["passes"]
                    else "Walk-forward du filtre non validé"
                )
                st.badge(
                    strength_walk_text,
                    icon=":material/filter_list:",
                    color=strength_walk_color,
                )
                st.dataframe(
                    pd.DataFrame(strength_walk["folds"]),
                    hide_index=True,
                    column_config={
                        "pli": st.column_config.NumberColumn("Pli"),
                        "début_test": st.column_config.DatetimeColumn("Début du test"),
                        "fin_test": st.column_config.DatetimeColumn("Fin du test"),
                        "seuil": None,
                        "libellé": st.column_config.TextColumn("Filtre choisi", pinned=True),
                        "rendement_test_stressé": st.column_config.NumberColumn(
                            "Rendement stressé", format="%.3f %%"
                        ),
                        "rendement_sans_filtre_stressé": st.column_config.NumberColumn(
                            "Sans filtre", format="%.3f %%"
                        ),
                        "écart_vs_sans_filtre": st.column_config.NumberColumn(
                            "Écart", format="%+.3f point"
                        ),
                        "positif": st.column_config.CheckboxColumn("Positif"),
                        "surperforme": st.column_config.CheckboxColumn("Surperforme"),
                    },
                )
                st.caption(
                    "Validation requise : au moins 2 plis positifs et 2 plis meilleurs que la "
                    "stratégie sans filtre. Le filtre actif reste inchangé."
                )
            elif strength_validation:
                st.info(
                    "Historique insuffisant pour le walk-forward du filtre avec ces moyennes.",
                    icon=":material/info:",
                )

        confirmation_lab = st.session_state.get("confirmation_lab")
        if confirmation_lab:
            st.subheader("Laboratoire anti-bruit", anchor=False)
            st.write(
                "Le même croisement de moyennes est testé immédiatement, puis après deux ou "
                "trois bougies consécutives de confirmation. Le scénario stressé applique "
                "1 % de frais et 1 % de slippage à chaque exécution."
            )
            lowest = confirmation_lab["lowest_turnover"]
            stressed = confirmation_lab["best_stressed"]
            with st.container(horizontal=True):
                st.metric(
                    "Trades immédiats",
                    confirmation_lab["baseline_trades"],
                    border=True,
                )
                st.metric(
                    "Rotation minimale",
                    lowest["libellé"],
                    f"{lowest['trades']} trades",
                    border=True,
                )
                st.metric(
                    "Meilleur rendement stressé",
                    stressed["libellé"],
                    f"{stressed['rendement_stress']:+.3f} %",
                    border=True,
                )
            st.badge(
                "Expérience uniquement — aucune promotion automatique",
                icon=":material/science:",
                color="blue",
            )
            confirmation_frame = pd.DataFrame(confirmation_lab["variants"])
            chart_frame = confirmation_frame.melt(
                id_vars="libellé",
                value_vars=["rendement_normal", "rendement_stress"],
                var_name="conditions",
                value_name="rendement",
            )
            confirmation_chart = (
                alt.Chart(chart_frame)
                .mark_bar()
                .encode(
                    x=alt.X("libellé:N", title="Confirmation", sort=None),
                    y=alt.Y("rendement:Q", title="Rendement (%)"),
                    xOffset="conditions:N",
                    color=alt.Color(
                        "conditions:N",
                        title="Conditions",
                        scale=alt.Scale(
                            domain=["rendement_normal", "rendement_stress"],
                            range=["#22c55e", "#f97316"],
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("libellé:N", title="Confirmation"),
                        alt.Tooltip("conditions:N", title="Conditions"),
                        alt.Tooltip("rendement:Q", title="Rendement (%)", format="+.3f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(confirmation_chart)
            st.dataframe(
                confirmation_frame,
                hide_index=True,
                column_config={
                    "confirmation": None,
                    "libellé": st.column_config.TextColumn("Confirmation", pinned=True),
                    "rendement_normal": st.column_config.NumberColumn(
                        "Rendement normal", format="%.3f %%"
                    ),
                    "rendement_stress": st.column_config.NumberColumn(
                        "Rendement stressé", format="%.3f %%"
                    ),
                    "érosion_coûts": st.column_config.NumberColumn(
                        "Érosion coûts", format="%.3f point"
                    ),
                    "drawdown": st.column_config.NumberColumn("Drawdown", format="%.3f %%"),
                    "facteur_profit": st.column_config.NumberColumn(
                        "Facteur profit", format="%.3f"
                    ),
                    "espérance": st.column_config.NumberColumn("Espérance", format="$%.2f"),
                },
            )
            st.caption(
                "Une confirmation réduit parfois les faux signaux, mais retarde aussi les entrées "
                "et sorties. Ces résultats historiques doivent être confirmés hors échantillon."
            )

            confirmation_validation = st.session_state.get("confirmation_validation")
            if confirmation_validation:
                st.markdown("#### Test futur séparé")
                st.write(
                    f"La confirmation est choisie uniquement sur les "
                    f"**{confirmation_validation['train_count']} premières bougies**, puis figée "
                    f"et testée sur les **{confirmation_validation['test_count']} suivantes**."
                )
                with st.container(horizontal=True):
                    st.metric(
                        "Choix sur entraînement",
                        confirmation_validation["selected_label"],
                        f"{confirmation_validation['training_stressed_return']:+.3f} % stressé",
                        border=True,
                    )
                    st.metric(
                        "Résultat futur stressé",
                        f"{confirmation_validation['test_stressed_return']:+.3f} %",
                        border=True,
                    )
                    st.metric(
                        "Écart face à l’immédiat",
                        f"{confirmation_validation['excess_return_percent']:+.3f} point",
                        border=True,
                    )
                    st.metric(
                        "Trades futurs",
                        confirmation_validation["test_trades"],
                        border=True,
                    )
                validation_color = "green" if confirmation_validation["passes"] else "red"
                validation_text = (
                    "Confirmation validée hors échantillon sous stress"
                    if confirmation_validation["passes"]
                    else "Confirmation non validée hors échantillon"
                )
                st.badge(
                    validation_text,
                    icon=":material/experiment:",
                    color=validation_color,
                )
                training_frame = pd.DataFrame(
                    confirmation_validation["training_results"]
                )
                st.dataframe(
                    training_frame,
                    hide_index=True,
                    column_config={
                        "confirmation": None,
                        "libellé": st.column_config.TextColumn("Confirmation", pinned=True),
                        "rendement_normal": st.column_config.NumberColumn(
                            "Entraînement normal", format="%.3f %%"
                        ),
                        "rendement_stress": st.column_config.NumberColumn(
                            "Entraînement stressé", format="%.3f %%"
                        ),
                    },
                )
                st.caption(
                    f"Coupure chronologique : {confirmation_validation['split_date']:%d/%m/%Y %H:%M} UTC. "
                    "Le test futur n’intervient jamais dans le choix de la confirmation."
                )

            confirmation_walk = st.session_state.get("confirmation_walk_forward")
            if confirmation_walk:
                st.markdown("#### Walk-forward des confirmations")
                st.write(
                    "Le choix 1/2/3 bougies est recalculé avant chaque fenêtre future, puis "
                    "figé pendant son test sous coûts extrêmes."
                )
                with st.container(horizontal=True):
                    st.metric(
                        "Plis positifs",
                        f"{confirmation_walk['positive_folds']} / {confirmation_walk['fold_count']}",
                        border=True,
                    )
                    st.metric(
                        "Plis surperformants",
                        f"{confirmation_walk['outperforming_folds']} / {confirmation_walk['fold_count']}",
                        border=True,
                    )
                    st.metric(
                        "Rendement futur moyen",
                        f"{confirmation_walk['average_test_return']:+.3f} %",
                        border=True,
                    )
                    st.metric(
                        "Avantage moyen",
                        f"{confirmation_walk['average_excess_return']:+.3f} point",
                        border=True,
                    )
                walk_color = "green" if confirmation_walk["passes"] else "red"
                walk_text = (
                    "Walk-forward anti-bruit validé"
                    if confirmation_walk["passes"]
                    else "Walk-forward anti-bruit non validé"
                )
                st.badge(walk_text, icon=":material/route:", color=walk_color)
                confirmation_folds = pd.DataFrame(confirmation_walk["folds"])
                st.dataframe(
                    confirmation_folds,
                    hide_index=True,
                    column_config={
                        "pli": st.column_config.NumberColumn("Pli"),
                        "début_test": st.column_config.DatetimeColumn("Début du test"),
                        "fin_test": st.column_config.DatetimeColumn("Fin du test"),
                        "confirmation": None,
                        "libellé": st.column_config.TextColumn("Choix", pinned=True),
                        "rendement_test_stressé": st.column_config.NumberColumn(
                            "Rendement stressé", format="%.3f %%"
                        ),
                        "rendement_immédiat_stressé": st.column_config.NumberColumn(
                            "Immédiat stressé", format="%.3f %%"
                        ),
                        "écart_vs_immédiat": st.column_config.NumberColumn(
                            "Écart", format="%+.3f point"
                        ),
                        "positif": st.column_config.CheckboxColumn("Positif"),
                        "surperforme": st.column_config.CheckboxColumn("Surperforme"),
                    },
                )
                st.caption(
                    "Le verdict exige au moins 2 plis positifs et 2 plis au moins aussi bons que "
                    "le signal immédiat. Aucun pli futur ne participe à son propre choix."
                )
            elif confirmation_validation:
                st.info(
                    "Historique insuffisant pour le walk-forward avec ces moyennes mobiles.",
                    icon=":material/info:",
                )

        validation = st.session_state.get("out_of_sample")
        if validation:
            st.subheader("Validation hors échantillon", anchor=False)
            st.write(
                f"Jarvis a utilisé **{validation['train_count']} bougies** pour choisir entre "
                "les variantes 3/8, 5/12 et 8/16. Il a ensuite figé ce choix et l’a évalué "
                f"sur les **{validation['test_count']} bougies suivantes**, à partir du "
                f"{validation['split_date'].strftime('%d/%m/%Y %H:%M UTC')}."
            )
            selected_label = (
                f"{validation['selected_short']}/{validation['selected_long']}"
            )
            test_result = validation["test_result"]
            benchmark_result = validation["benchmark_result"]
            with st.container(horizontal=True):
                st.metric("Paramètres choisis", selected_label, border=True)
                st.metric(
                    "Rendement entraînement",
                    f"{validation['training_return_percent']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Rendement test invisible",
                    f"{test_result['return_percent']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Buy & hold sur le test",
                    f"{benchmark_result['return_percent']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Surperformance",
                    f"{validation['excess_return_percent']:+.3f} %",
                    border=True,
                )
            status_color = "green" if validation["passes"] else "red"
            status_text = "Validation réussie" if validation["passes"] else "Validation non concluante"
            st.badge(status_text, icon=":material/fact_check:", color=status_color)
            training_table = pd.DataFrame(validation["training_results"])
            with st.expander("Voir la sélection sur l’entraînement", icon=":material/analytics:"):
                st.dataframe(
                    training_table,
                    hide_index=True,
                    column_config={
                        "short": st.column_config.NumberColumn("Moyenne courte"),
                        "long": st.column_config.NumberColumn("Moyenne longue"),
                        "return_percent": st.column_config.NumberColumn(
                            "Rendement", format="%.3f %%"
                        ),
                        "drawdown_percent": st.column_config.NumberColumn(
                            "Drawdown", format="%.3f %%"
                        ),
                    },
                )
            st.caption(
                "Cette validation réduit le risque de surapprentissage, mais une seule séparation "
                "temporelle ne suffit pas pour conclure."
            )

        walk_forward = st.session_state.get("walk_forward")
        if walk_forward:
            st.subheader("Validation walk-forward", anchor=False)
            st.write(
                "À chaque pli, Jarvis réentraîne la sélection sur tout le passé disponible, "
                "puis teste les paramètres figés sur une nouvelle fenêtre future disjointe. "
                "Les frais, le slippage et le benchmark buy & hold restent identiques."
            )
            with st.container(horizontal=True):
                st.metric(
                    "Plis positifs",
                    f"{walk_forward['positive_folds']} / {walk_forward['fold_count']}",
                    border=True,
                )
                st.metric(
                    "Plis au-dessus du buy & hold",
                    f"{walk_forward['outperforming_folds']} / {walk_forward['fold_count']}",
                    border=True,
                )
                st.metric(
                    "Rendement test moyen",
                    f"{walk_forward['average_test_return']:+.3f} %",
                    border=True,
                )
                st.metric(
                    "Benchmark moyen",
                    f"{walk_forward['average_benchmark_return']:+.3f} %",
                    border=True,
                )
            walk_color = "green" if walk_forward["passes"] else "red"
            walk_status = (
                "Robustesse multi-fenêtres réussie"
                if walk_forward["passes"]
                else "Robustesse multi-fenêtres non concluante"
            )
            st.badge(walk_status, icon=":material/view_timeline:", color=walk_color)

            fold_frame = pd.DataFrame(walk_forward["folds"])
            st.dataframe(
                fold_frame,
                hide_index=True,
                column_config={
                    "pli": st.column_config.NumberColumn("Pli"),
                    "début_test": st.column_config.DatetimeColumn(
                        "Début du test", format="DD/MM/YYYY HH:mm"
                    ),
                    "fin_test": st.column_config.DatetimeColumn(
                        "Fin du test", format="DD/MM/YYYY HH:mm"
                    ),
                    "rendement_entraînement": st.column_config.NumberColumn(
                        "Entraînement", format="%.3f %%"
                    ),
                    "rendement_test": st.column_config.NumberColumn(
                        "Test", format="%.3f %%"
                    ),
                    "rendement_benchmark": st.column_config.NumberColumn(
                        "Buy & hold", format="%.3f %%"
                    ),
                    "surperformance": st.column_config.NumberColumn(
                        "Surperformance", format="%.3f %%"
                    ),
                },
            )
            fold_chart = fold_frame[["pli", "rendement_test", "rendement_benchmark"]].melt(
                id_vars="pli",
                var_name="série",
                value_name="rendement",
            )
            fold_chart["série"] = fold_chart["série"].replace(
                {
                    "rendement_test": "Stratégie sélectionnée",
                    "rendement_benchmark": "Buy & hold",
                }
            )
            st.bar_chart(
                fold_chart,
                x="pli",
                y="rendement",
                color="série",
                stack=False,
            )
            st.caption(
                "Trois plis réduisent la dépendance à une seule date de séparation, "
                "mais ne prouvent pas une performance future."
            )
        elif result:
            st.info(
                "Le walk-forward nécessite au moins 120 bougies. "
                "Relance le backtest avec 120 bougies ou plus.",
                icon=":material/view_timeline:",
            )

        readiness = st.session_state.get("validation_readiness")
        if readiness:
            st.divider()
            st.subheader("Verdict global de validation", anchor=False)
            with st.container(border=True):
                with st.container(horizontal=True):
                    st.metric(
                        "Score de validation",
                        f"{readiness['score']} / 100",
                        border=True,
                    )
                    st.metric(
                        "Barrières validées",
                        f"{readiness['passed_count']} / {readiness['check_count']}",
                        border=True,
                    )
                    st.metric("Statut d’exécution", "Réel verrouillé", border=True)
                st.badge(
                    readiness["status"],
                    icon=":material/verified_user:",
                    color=readiness["color"],
                )
                st.write(readiness["recommendation"])
                readiness_frame = pd.DataFrame(readiness["checks"])
                st.dataframe(
                    readiness_frame,
                    hide_index=True,
                    column_config={
                        "contrôle": st.column_config.TextColumn("Contrôle", pinned=True),
                        "réussi": st.column_config.CheckboxColumn("Réussi"),
                        "résultat": st.column_config.TextColumn("Résultat observé"),
                    },
                )
                if readiness["actions"]:
                    st.markdown("**Plan d’amélioration prioritaire**")
                    st.dataframe(
                        pd.DataFrame(readiness["actions"]),
                        hide_index=True,
                        column_config={
                            "priorité": st.column_config.TextColumn("Priorité", pinned=True),
                            "barrière": st.column_config.TextColumn("Barrière"),
                            "constat": st.column_config.TextColumn("Constat", width="medium"),
                            "action recommandée": st.column_config.TextColumn(
                                "Action recommandée", width="large"
                            ),
                            "objectif du prochain test": st.column_config.TextColumn(
                                "Objectif mesurable", width="large"
                            ),
                        },
                    )
                    st.caption(
                        "Ces actions sont des pistes de recherche. Elles ne modifient ni les "
                        "paramètres ni les règles de trading sans validation humaine."
                    )
                else:
                    st.success(
                        "Aucune action corrective ouverte pour cette validation.",
                        icon=":material/task_alt:",
                    )
                report = st.session_state.get("backtest_report")
                if report:
                    report_json = export_backtest_report(report)
                    st.caption(
                        f"Empreinte SHA-256 : `{report['empreinte_sha256']}`"
                    )
                    st.download_button(
                        "Télécharger le rapport de validation",
                        data=report_json,
                        file_name=(
                            "jdegen_backtest_"
                            f"{report['généré_le'][:19].replace(':', '-')}"
                            ".json"
                        ),
                        mime="application/json",
                        icon=":material/download:",
                        type="primary",
                    )
            st.caption(
                "Ce verdict est une barrière de gouvernance interne. Même un score de 100/100 "
                "autorise seulement le paper trading supervisé, jamais une transaction réelle."
            )
            cross_market = st.session_state.get("cross_market_validation")
            candidate = st.session_state.get("strategy_candidate")
            paper_policy = st.session_state.get("paper_policy")
            paper_drift = st.session_state.get("paper_drift")
            if cross_market and candidate and paper_policy and paper_drift:
                st.subheader("Certification du cycle de vie", anchor=False)
                with st.container(horizontal=True):
                    st.metric("Marchés disponibles", cross_market["marchés_disponibles"], border=True)
                    st.metric("Marchés positifs", f"{cross_market['marchés_positifs']} / {cross_market['marchés_requis']}", border=True)
                    st.metric("Candidat", candidate["statut"], border=True)
                    st.metric("Paper supervisé", "ARMÉ" if paper_policy["paper_automatique_armé"] else "DÉSARMÉ", border=True)
                    st.metric("Dérive paper", paper_drift["statut"], border=True)
                st.badge(
                    "Trading réel impossible — aucun wallet ni SDK de transaction",
                    icon=":material/lock:", color="green",
                )
                if cross_market["marchés"]:
                    st.dataframe(
                        pd.DataFrame(cross_market["marchés"]).drop(columns=["variantes"]),
                        hide_index=True,
                        column_config={"marché": st.column_config.TextColumn("Marché", pinned=True),
                                       "rendement_stressé": st.column_config.NumberColumn("Rendement stressé", format="%.3f %%"),
                                       "drawdown": st.column_config.NumberColumn("Drawdown", format="%.3f %%"),
                                       "réussi": st.column_config.CheckboxColumn("Validé")},
                    )
                if candidate["raisons"]:
                    st.warning("Candidat refusé : " + " ; ".join(candidate["raisons"]), icon=":material/block:")
                st.caption(
                    "Le mode paper automatique reste soumis à une approbation humaine par ordre, "
                    "à 2 % maximum par position, trois positions maximum et 3 % de perte journalière."
                )
            archive_status = verify_backtest_archive()
            archived_reports = list_backtest_reports(limit=25)
            st.subheader("Historique des validations", anchor=False)
            archive_color = "green" if archive_status["valid"] else "red"
            archive_label = (
                "Archive intègre"
                if archive_status["valid"]
                else "Archive altérée"
            )
            with st.container(horizontal=True):
                st.metric("Rapports archivés", archive_status["count"], border=True)
                st.badge(
                    archive_label,
                    icon=":material/database:",
                    color=archive_color,
                )
            history_summary = summarize_backtest_history(archived_reports)
            score_delta = history_summary.get("score_delta")
            return_delta = history_summary.get("return_delta")
            with st.container(horizontal=True):
                st.metric(
                    "Dernier score",
                    f"{history_summary['latest_score']} / 100",
                    (
                        f"{score_delta:+d} points vs précédent"
                        if score_delta is not None
                        else None
                    ),
                    border=True,
                )
                st.metric(
                    "Dernier rendement",
                    f"{history_summary['latest_return']:+.3f} %",
                    (
                        f"{return_delta:+.3f} point vs précédent"
                        if return_delta is not None
                        else None
                    ),
                    border=True,
                )
                st.metric(
                    "Meilleur score archivé",
                    f"{history_summary['best_score']} / 100",
                    history_summary["best_market"],
                    border=True,
                )
            if history_summary["count"] >= 2:
                trend_frame = pd.DataFrame(history_summary["trend"])
                trend_frame["date"] = pd.to_datetime(trend_frame["date"], utc=True)
                trend_columns = st.columns(2)
                with trend_columns[0]:
                    st.markdown("**Évolution du score**")
                    st.line_chart(
                        trend_frame,
                        x="date",
                        y="score",
                        y_label="Score / 100",
                    )
                with trend_columns[1]:
                    st.markdown("**Évolution du rendement**")
                    st.line_chart(
                        trend_frame,
                        x="date",
                        y="rendement",
                        y_label="Rendement (%)",
                    )
            else:
                st.info(
                    "Lance un second backtest pour afficher l’évolution du score et du rendement.",
                    icon=":material/trending_up:",
                )
            history_rows = [
                {
                    "date": report["généré_le"],
                    "marché": report["marché"],
                    "paramètres": (
                        f"{report['paramètres']['moyenne_courte']}/"
                        f"{report['paramètres']['moyenne_longue']}"
                    ),
                    "score": report["verdict"]["score"],
                    "statut": report["verdict"]["statut"],
                    "rendement": report["résultat"]["rendement_pourcent"],
                    "intègre": report["intègre"],
                    "empreinte": report["empreinte_sha256"][:12],
                }
                for report in archived_reports
            ]
            st.dataframe(
                pd.DataFrame(history_rows),
                hide_index=True,
                column_config={
                    "date": st.column_config.DatetimeColumn(
                        "Date du test", format="DD/MM/YYYY HH:mm"
                    ),
                    "score": st.column_config.ProgressColumn(
                        "Score", min_value=0, max_value=100, format="%d / 100"
                    ),
                    "rendement": st.column_config.NumberColumn(
                        "Rendement", format="%.3f %%"
                    ),
                    "intègre": st.column_config.CheckboxColumn("Intègre"),
                    "empreinte": st.column_config.TextColumn("Empreinte courte"),
                },
            )
            st.caption(
                "Chaque clic sur « Lancer le backtest » crée un rapport unique. Une même "
                "empreinte ne peut être archivée qu’une fois."
            )
    else:
        st.info(
            "Configure les paramètres puis lance le premier backtest.",
            icon=":material/science:",
        )

with social_tab:
    st.subheader("Brouillons sociaux vérifiables", anchor=False)
    st.write(
        "Jarvis transforme la dernière décision auditée en brouillons pour X et Telegram. "
        "La génération reste locale et aucune publication automatique n’est possible."
    )
    st.markdown(":orange-badge[Brouillon uniquement] :blue-badge[Validation humaine obligatoire]")

    if st.session_state.decisions:
        latest = st.session_state.decisions[0]
        fingerprint = str(latest.get("empreinte", "non-disponible"))[:12]
        with st.container(border=True):
            st.caption("SOURCE DU BROUILLON")
            with st.container(horizontal=True):
                st.metric("Marché", latest.get("marché", "—"), border=True)
                st.metric("Signal", latest.get("action", "WAIT"), border=True)
                st.metric("Score", f"{float(latest.get('score', 0)):+.0f}", border=True)
                st.metric(
                    "Confiance",
                    f"{float(latest.get('confiance', 0)):.0%}",
                    border=True,
                )
            st.caption(f"Empreinte d’audit : `{fingerprint}…`")

        tone = st.segmented_control(
            "Personnalité de Jarvis",
            options=list(TONES),
            default="Sarcastique",
            selection_mode="single",
        ) or "Sarcastique"
        drafts = generate_social_drafts(latest, tone)
        draft_key = f"{latest.get('audit_id', fingerprint)}_{tone}"
        x_draft = st.text_area(
            "Brouillon X",
            value=drafts["x"],
            height=150,
            key=f"x_{draft_key}",
        )
        x_color = "green" if len(x_draft) <= 280 else "red"
        st.badge(f"{len(x_draft)} / 280 caractères", color=x_color)
        telegram_draft = st.text_area(
            "Brouillon Telegram",
            value=drafts["telegram"],
            height=330,
            key=f"telegram_{draft_key}",
        )

        approved = st.checkbox(
            "J’ai relu les chiffres et j’approuve ces brouillons pour export.",
            key=f"approval_{draft_key}",
        )
        export_payload = json.dumps(
            {
                "source_audit": latest,
                "ton": tone,
                "brouillons": {"x": x_draft, "telegram": telegram_draft},
                "validation_humaine": approved,
            },
            ensure_ascii=False,
            indent=2,
        )
        st.download_button(
            "Exporter les brouillons approuvés",
            data=export_payload,
            file_name=f"jdegen_brouillons_{fingerprint}.json",
            mime="application/json",
            icon=":material/download:",
            disabled=not approved or len(x_draft) > 280,
        )
        st.caption(
            "L’export prépare un fichier local. Il ne contacte ni X ni Telegram et ne publie rien."
        )
    else:
        st.info(
            "Lance d’abord une analyse dans la barre latérale pour créer une décision auditée.",
            icon=":material/edit_note:",
        )

with audit_tab:
    st.subheader("Centre de contrôle avant lancement", anchor=False)
    st.write(
        "Ces contrôles vérifient automatiquement les frontières du prototype. Un résultat positif "
        "autorise seulement une revue humaine approfondie, jamais le trading réel."
    )
    audit = run_launch_audit(ROOT, verify_chain())
    with st.container(horizontal=True):
        st.metric("Contrôles réussis", f"{audit['passed']} / {audit['total']}", border=True)
        st.metric("Points bloquants", audit["blockers"], border=True)
        st.metric("Trading réel", "Désactivé", border=True)

    if audit["review_ready"]:
        st.success(
            "Le prototype est prêt pour une revue humaine. Le passage au réel reste verrouillé.",
            icon=":material/fact_check:",
        )
    else:
        st.error(
            "La revue ne peut pas commencer tant que les points bloquants ne sont pas corrigés.",
            icon=":material/block:",
        )

    audit_frame = pd.DataFrame(audit["checks"])
    st.dataframe(
        audit_frame,
        hide_index=True,
        column_config={
            "contrôle": st.column_config.TextColumn("Contrôle", pinned=True),
            "statut": st.column_config.TextColumn("Statut"),
            "preuve": st.column_config.TextColumn("Preuve", width="large"),
        },
    )
    st.subheader("Vérifier un rapport de Backtest", anchor=False)
    st.write(
        "Importe un rapport JSON exporté depuis JDEGEN. La vérification s’effectue localement "
        "et le fichier importé n’est pas ajouté automatiquement à l’archive."
    )
    uploaded_report = st.file_uploader(
        "Rapport de validation JSON",
        type="json",
        key="backtest_report_verifier",
        max_upload_size=1,
        help="Taille maximale : 1 Mo. Seul le format jdegen-backtest-report-v1 est accepté.",
    )
    if uploaded_report is not None:
        inspection = inspect_backtest_report(uploaded_report.getvalue())
        if inspection["valid"]:
            imported = inspection["report"]
            st.success(inspection["reason"], icon=":material/verified:")
            with st.container(horizontal=True):
                st.metric("Marché importé", imported["marché"], border=True)
                st.metric(
                    "Score importé",
                    f"{imported['verdict']['score']} / 100",
                    border=True,
                )
                st.metric(
                    "Statut importé",
                    imported["verdict"]["statut"],
                    border=True,
                )
                st.metric(
                    "Rendement importé",
                    f"{imported['résultat']['rendement_pourcent']:+.3f} %",
                    border=True,
                )
            st.caption(
                f"Empreinte vérifiée : `{imported['empreinte_sha256']}`"
            )
        else:
            st.error(inspection["reason"], icon=":material/gpp_bad:")
    report = json.dumps(
        {
            "généré_le": datetime.now(UTC).isoformat(),
            "verdict": "PRÊT POUR REVUE" if audit["review_ready"] else "BLOQUÉ",
            **audit,
        },
        ensure_ascii=False,
        indent=2,
    )
    st.download_button(
        "Exporter le rapport de contrôle",
        data=report,
        file_name="jdegen_controle_avant_lancement.json",
        mime="application/json",
        icon=":material/download:",
    )
    st.warning(
        "Limite volontaire : ce rapport ne constitue ni un audit de sécurité indépendant, "
        "ni une autorisation de déploiement, ni un conseil financier.",
        icon=":material/lock:",
    )

with concept_tab:
    st.subheader("Une expérience d’agent autonome, vérifiable publiquement", anchor=False)
    st.write(
        "JarvisDegen combine analyse de marché, règles de risque et personnalité sociale. "
        "L’objectif du MVP est d’abord de démontrer un processus reproductible et transparent."
    )
    concept_columns = st.columns(3)
    with concept_columns[0].container(border=True, height="stretch"):
        st.markdown("### :material/query_stats: Observer")
        st.write("Collecter prix, volume, liquidité et sentiment depuis des sources identifiées.")
    with concept_columns[1].container(border=True, height="stretch"):
        st.markdown("### :material/psychology: Décider")
        st.write("Produire un signal explicable, puis appliquer les limites de risque avant toute action.")
    with concept_columns[2].container(border=True, height="stretch"):
        st.markdown("### :material/visibility: Prouver")
        st.write("Conserver chaque décision et publier les preuves vérifiables par la communauté.")
    st.info(
        "La phase actuelle s’arrête volontairement avant la signature et l’envoi de transactions.",
        icon=":material/info:",
    )

with tokenomics_tab:
    st.subheader("Une boucle économique simple", anchor=False)
    allocation = pd.DataFrame(
        {"Destination": ["Capital de re-trading", "Buyback & burn"], "Part": [70, 30]}
    )
    chart_col, explanation_col = st.columns([1.2, 1])
    with chart_col.container(border=True):
        st.bar_chart(allocation, x="Destination", y="Part", horizontal=True)
    with explanation_col.container(border=True, height="stretch"):
        st.metric("Réinvestissement", "70 %")
        st.write("Alimente le capital de trading pour les opportunités futures.")
        st.metric("Buyback & burn", "30 %")
        st.write("Rachat public de $JDEGEN puis destruction vérifiable des jetons.")
    st.warning(
        "Cette mécanique est une spécification cible. Elle n’est pas active dans le MVP et devra être auditée.",
        icon=":material/warning:",
    )

with roadmap_tab:
    st.subheader("Construction progressive", anchor=False)
    milestones = [
        ("01", "Socle sécurisé", "Terminé", "Simulation, moteur de risque et journal d’audit."),
        ("02", "Identité & vitrine", "En cours", "Interface publique, concept, tokenomics et roadmap."),
        ("03", "Données Solana", "Terminé", "Prix, volume, liquidité et santé réseau en lecture seule."),
        ("04", "Stratégie simulée", "Terminé", "Score explicable, paper trading et premier moteur de backtest."),
        ("05", "Transparence", "En cours", "Journal persistant, chaîne SHA-256 et exports auditables."),
        ("06", "Communication", "En cours", "Brouillons X et Telegram reliés aux preuves, avec validation humaine."),
        ("07", "Audit & décision", "En cours", "Centre de contrôle automatique avant revue de sécurité indépendante."),
    ]
    for number, title, status, description in milestones:
        with st.container(border=True):
            row = st.columns([0.35, 1.2, 0.7, 3], vertical_alignment="center")
            row[0].markdown(f"**{number}**")
            row[1].markdown(f"**{title}**")
            badge_color = "green" if status == "Terminé" else "blue" if status == "En cours" else "gray"
            row[2].badge(status, color=badge_color)
            row[3].write(description)

with st.expander("Garde-fous actifs", icon=":material/security:"):
    st.write(
        "Position ≤ 2 % du capital • perte quotidienne ≤ 3 % • "
        "trois positions maximum • confiance ≥ 70 %"
    )
    st.warning(
        "Le passage au trading réel reste bloqué et fera l’objet d’une étape séparée.",
        icon=":material/lock:",
    )
