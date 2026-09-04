"""Forsikringstilbod.

Bilen må vere forsikra frå det sekundet han står i kjøparen sitt namn. Difor
spør vi kjøparen om forsikring før eigarskiftet, ikkje etter.

I produksjon: prisspørjing mot fleire selskap (Gjensidige, If, Fremtind, Tryg)
via meklar-API, og teikning med kjøparen sitt samtykke. Her: ein rekna pris ut
frå bilen, slik at flyten og talformatet er ekte sjølv om tilboda ikkje er det.
"""

from __future__ import annotations

from datetime import date

SELSKAP = [
    ("Fjordvern", 1.00, "Ansvar + kasko, 6 000 kr eigendel"),
    ("Nordlys Forsikring", 0.88, "Ansvar + delkasko, 8 000 kr eigendel"),
    ("Kystbil", 1.14, "Ansvar + kasko, 4 000 kr eigendel, leigebil"),
]


def _grunnpris(bil: dict, pris: int) -> int:
    alder = max(0, date.today().year - int(bil.get("aarsmodell", date.today().year)))
    verdi_del = pris * 0.018
    alders_del = max(0, 8 - alder) * 190
    el_rabatt = 0.9 if bil.get("drivstoff") == "Elektrisk" else 1.0
    return int((2400 + verdi_del + alders_del) * el_rabatt)


def tilbod(bil: dict, pris: int, alder_kjopar: int = 35) -> list:
    """Årspris frå kvart selskap, billegast først."""
    ung = 1.35 if alder_kjopar < 25 else 1.0
    grunn = _grunnpris(bil, pris)
    ut = [
        {
            "selskap": namn,
            "dekning": tekst,
            "aarspris": int(grunn * faktor * ung),
            "maanadspris": int(grunn * faktor * ung / 12),
        }
        for namn, faktor, tekst in SELSKAP
    ]
    return sorted(ut, key=lambda t: t["aarspris"])


def teikn(selskap: str, tilboda: list) -> dict:
    valt = next((t for t in tilboda if t["selskap"] == selskap), None)
    if not valt:
        raise ValueError("Ukjent selskap")
    return dict(valt, status="teikna", gjeld_frå="ved eigarskifte")
