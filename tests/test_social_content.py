import pytest

from social_content import TONES, generate_social_drafts


RECORD = {
    "marché": "SOL/USDC",
    "action": "BUY",
    "statut": "APPROUVÉ",
    "score": 65,
    "confiance": 0.95,
    "prix_usd": 187.42,
    "position_usd": 200,
    "raison": "Tous les garde-fous sont respectés",
    "empreinte": "abcdef1234567890",
}


@pytest.mark.parametrize("tone", TONES)
def test_x_draft_is_factual_and_fits_limit(tone):
    draft = generate_social_drafts(RECORD, tone)["x"]
    assert len(draft) <= 280
    assert "SIMULATION" in draft
    assert "SOL/USDC" in draft
    assert "#abcdef123456" in draft


def test_telegram_explicitly_denies_real_execution():
    draft = generate_social_drafts(RECORD)["telegram"]
    assert "DÉCISION SIMULÉE" in draft
    assert "aucune transaction réelle" in draft
    assert "Tous les garde-fous sont respectés" in draft


def test_unknown_tone_is_rejected():
    with pytest.raises(ValueError):
        generate_social_drafts(RECORD, "Inconnu")
