"""Brouillons sociaux déterministes fondés sur une décision auditée."""

from __future__ import annotations


TONES = ("Sarcastique", "Sobre", "Degen")


def _percent(value: float) -> str:
    return f"{float(value) * 100:.0f} %"


def _price(value: float) -> str:
    number = float(value)
    return f"${number:,.6f}" if number < 10 else f"${number:,.2f}"


def generate_social_drafts(record: dict, tone: str = "Sarcastique") -> dict[str, str]:
    """Génère des brouillons X et Telegram sans aucune affirmation d'exécution réelle."""
    if tone not in TONES:
        raise ValueError(f"Ton inconnu : {tone}")

    market = str(record.get("marché", "marché inconnu"))
    action = str(record.get("action", "WAIT")).upper()
    status = str(record.get("statut", "OBSERVATION"))
    score = int(record.get("score", 0))
    confidence = _percent(record.get("confiance", 0))
    price = _price(record.get("prix_usd", 0))
    position = float(record.get("position_usd", 0))
    reason = str(record.get("raison", "Règles de simulation appliquées"))
    fingerprint = str(record.get("empreinte", "non-disponible"))[:12]

    flourishes = {
        "Sarcastique": "Les chiffres ont parlé. Pour une fois, personne ne les a interrompus.",
        "Sobre": "Décision fondée sur les données observées et les garde-fous actifs.",
        "Degen": "Le signal chauffe, mais le bouton réel reste sous cadenas. Discipline d'abord.",
    }
    flourish = flourishes[tone]
    size_text = f"Position simulée : ${position:,.2f}." if position else "Aucune position simulée."

    x = (
        f"SIMULATION • {market} • {action} ({status}) à {price}. "
        f"Score {score:+d}, confiance {confidence}. {size_text} "
        f"{flourish} Preuve #{fingerprint} — $JDEGEN"
    )
    if len(x) > 280:
        x = (
            f"SIMULATION • {market} • {action} ({status}) à {price}. "
            f"Score {score:+d}, confiance {confidence}. {size_text} "
            f"Preuve #{fingerprint} — $JDEGEN"
        )

    telegram = "\n".join(
        [
            "🤖 JARVISDEGEN — DÉCISION SIMULÉE",
            "",
            f"Marché : {market}",
            f"Signal : {action}",
            f"Statut : {status}",
            f"Prix observé : {price}",
            f"Score : {score:+d} | Confiance : {confidence}",
            size_text,
            f"Règle appliquée : {reason}",
            "",
            flourish,
            f"Preuve d’audit : #{fingerprint}",
            "",
            "⚠️ Simulation uniquement — aucune transaction réelle, aucun conseil financier.",
        ]
    )
    return {"x": x, "telegram": telegram}
