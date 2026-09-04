"""Billån.

Mange bruktbilkjøp blir finansierte. Får kjøparen svar på lånet inne i appen,
slepp han å hoppe ut av handelen midt i.

I produksjon: søknad til fleire bankar samstundes, med kredittsjekk og
samtykke. Her: annuitetsrekning med realistiske rentesatsar, slik at tala i
grensesnittet er rette rekneskapsmessig sjølv om tilboda er oppdikta.
"""

from __future__ import annotations

from datetime import date

BANKAR = [
    ("Santander", 8.45),
    ("Nordea Finans", 7.90),
    ("Sparebanken Vest", 7.45),
]


def maanadsbelop(hovudstol: int, rente_aar: float, aar: int) -> int:
    """Annuitet: like store terminbeløp."""
    n = aar * 12
    r = rente_aar / 100 / 12
    if r == 0:
        return int(hovudstol / n)
    return int(hovudstol * r / (1 - (1 + r) ** -n))


def tilbod(bil: dict, pris: int, eigenkapital: int, aar: int = 5) -> list:
    """Lånetilbod for det kjøparen manglar. Tom liste om han ikkje treng lån."""
    hovudstol = max(0, pris - max(0, eigenkapital))
    if hovudstol <= 0:
        return []
    alder_bil = max(0, date.today().year - int(bil.get("aarsmodell", date.today().year)))
    paaslag = 0.6 if alder_bil > 8 else 0.0
    ut = []
    for namn, rente in BANKAR:
        r = rente + paaslag
        ut.append(
            {
                "bank": namn,
                "rente": round(r, 2),
                "aar": aar,
                "hovudstol": hovudstol,
                "maanadsbelop": maanadsbelop(hovudstol, r, aar),
                "etableringsgebyr": 1990,
            }
        )
    return sorted(ut, key=lambda t: t["maanadsbelop"])


def sok(bank: str, tilboda: list) -> dict:
    valt = next((t for t in tilboda if t["bank"] == bank), None)
    if not valt:
        raise ValueError("Ukjend bank")
    return dict(valt, status="førehandsgodkjent")
