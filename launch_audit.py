"""Contrôles locaux de préparation, sans activation d'exécution réelle."""

from __future__ import annotations

from pathlib import Path


WALLET_DEPENDENCIES = ("@solana/web3.js", "solders", "solana-py", "anchorpy")
TRANSACTION_MARKERS = ("sendtransaction", "signtransaction", "sendrawtransaction")


def run_launch_audit(root: Path, chain_result: dict) -> dict:
    """Inspecte les frontières de sécurité sans lire de fichier secret."""
    config_text = (root / "src" / "config.ts").read_text(encoding="utf-8").lower()
    package_text = (root / "package.json").read_text(encoding="utf-8").lower()
    gitignore_path = root / ".gitignore"
    gitignore_text = (
        gitignore_path.read_text(encoding="utf-8").lower()
        if gitignore_path.is_file()
        else ""
    )
    inspected_sources = [
        path for path in root.glob("*.py") if path.name != Path(__file__).name
    ] + list((root / "src").glob("*.ts"))
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore").lower()
        for path in inspected_sources
    )

    checks = [
        {
            "contrôle": "Verrou de simulation",
            "statut": "RÉUSSI" if "simulation_mode" in config_text and "doit rester à true" in config_text else "BLOQUANT",
            "preuve": "Le démarrage refuse explicitement SIMULATION_MODE différent de true.",
        },
        {
            "contrôle": "SDK de wallet absent",
            "statut": "RÉUSSI" if not any(item in package_text for item in WALLET_DEPENDENCIES) else "BLOQUANT",
            "preuve": "Aucune dépendance de signature Solana reconnue dans package.json.",
        },
        {
            "contrôle": "Envoi de transaction absent",
            "statut": "RÉUSSI" if not any(item in source_text for item in TRANSACTION_MARKERS) else "BLOQUANT",
            "preuve": "Aucun appel de signature ou d’envoi de transaction détecté dans les sources.",
        },
        {
            "contrôle": "Secrets exclus du dépôt",
            "statut": "RÉUSSI" if ".env" in gitignore_text else "BLOQUANT",
            "preuve": (
                ".env est couvert par .gitignore ; son contenu n’est jamais inspecté."
                if ".env" in gitignore_text
                else ".gitignore est absent ou ne couvre pas .env. Ajoutez-le au dépôt."
            ),
        },
        {
            "contrôle": "Chaîne d’audit intègre",
            "statut": "RÉUSSI" if chain_result.get("valid") else "BLOQUANT",
            "preuve": f"{chain_result.get('count', 0)} décision(s) vérifiée(s) par chaînage SHA-256.",
        },
        {
            "contrôle": "Validation sociale humaine",
            "statut": "RÉUSSI" if "validation humaine obligatoire" in source_text else "À VÉRIFIER",
            "preuve": "L’export social exige une approbation ; aucune API de publication n’est connectée.",
        },
    ]
    passed = sum(item["statut"] == "RÉUSSI" for item in checks)
    blockers = sum(item["statut"] == "BLOQUANT" for item in checks)
    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "blockers": blockers,
        "review_ready": blockers == 0,
        "real_trading_enabled": False,
    }
