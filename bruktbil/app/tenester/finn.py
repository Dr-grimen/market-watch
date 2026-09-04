"""Finn-lenke inn, skiltnummer ut.

I produksjon les vi annonsesida (eller Finn sitt API der vi får løyve) og
plukkar ut registreringsnummer, pris og kilometerstand. Her held vi oss til
lenkeforma, og lar demo-annonsar peike på demo-skilt.
"""

from __future__ import annotations

import re

from ..modell import Feil

DEMOANNONSAR = {
    "300000001": {"skilt": "DB12345", "pris": 179000},
    "300000002": {"skilt": "EL45678", "pris": 329000},
}

FINNKODE = re.compile(r"(?:finnkode=|/item/|/)(\d{6,12})")


def finnkode(lenke: str) -> str:
    treff = FINNKODE.search(lenke or "")
    if "finn.no" not in (lenke or "") or not treff:
        raise Feil("Dette ser ikkje ut som ei lenke til ein Finn-annonse.")
    return treff.group(1)


def les(lenke: str) -> dict:
    """{'skilt': ..., 'pris': ...} frå ei annonse-lenke."""
    kode = finnkode(lenke)
    if kode in DEMOANNONSAR:
        return dict(DEMOANNONSAR[kode], finnkode=kode)
    # Ukjend annonse i demoen: vi kan ikkje gjette skiltet, og skal ikkje late
    # som. Brukaren får skrive det inn sjølv.
    raise Feil(
        f"Fann annonse {kode}, men får ikkje ut skiltnummeret i demoen. "
        "Skriv inn skiltnummeret i staden."
    )
