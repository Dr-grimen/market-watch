"""Oppslag på skiltnummer.

I produksjon: Statens vegvesen sitt API for kjøretøyopplysningar, pluss
heftelsesregisteret (Brønnøysund) og eit verkstadhistorikk-oppslag.

Her: eit lite register med demo-bilar, og for alle andre skilt eit
deterministisk oppdikta kjøretøy, slik at kven som helst kan prøve flyten med
sitt eige skilt utan at vi jukser med at dette er ekte data. Alt som kjem ut
herifrå ber med seg `kjelde`, og appen viser kjelda til brukaren.
"""

from __future__ import annotations

import hashlib
from datetime import date

MERKE = [
    ("Volkswagen", "Golf"),
    ("Toyota", "RAV4"),
    ("Tesla", "Model 3"),
    ("Volvo", "V60"),
    ("Skoda", "Octavia"),
    ("Nissan", "Leaf"),
    ("BMW", "3-serie"),
    ("Ford", "Focus"),
]
DRIVSTOFF = ["Elektrisk", "Bensin", "Diesel", "Hybrid"]

DEMOREGISTER = {
    "DB12345": {
        "merke": "Volkswagen",
        "modell": "Golf 1.5 TSI",
        "aarsmodell": 2018,
        "drivstoff": "Bensin",
        "girkasse": "Manuell",
        "kilometerstand": 96500,
        "farge": "Mørk blå",
        "eigar": "Ola Nordmann",
        "eu_kontroll_frist": "2026-11-30",
        "heftingar": [],
        "avgift_betalt_til": "2026-12-31",
        "vraakt": False,
        "stolen": False,
        "importert": False,
        "eigarskifte_talet": 2,
    },
    "EL45678": {
        "merke": "Tesla",
        "modell": "Model 3 Long Range",
        "aarsmodell": 2021,
        "drivstoff": "Elektrisk",
        "girkasse": "Automat",
        "kilometerstand": 61200,
        "farge": "Kvit",
        "eigar": "Kari Nordmann",
        "eu_kontroll_frist": "2027-03-31",
        "heftingar": [{"långjevar": "Santander Consumer Bank", "belop": 145000}],
        "avgift_betalt_til": "2026-12-31",
        "vraakt": False,
        "stolen": False,
        "importert": False,
        "eigarskifte_talet": 1,
    },
}


def _frø(skilt: str) -> int:
    return int(hashlib.sha256(skilt.encode()).hexdigest()[:12], 16)


def _dikta_bil(skilt: str) -> dict:
    f = _frø(skilt)
    merke, modell = MERKE[f % len(MERKE)]
    aarsmodell = 2012 + (f >> 4) % 13
    alder = max(0, date.today().year - aarsmodell)
    return {
        "merke": merke,
        "modell": modell,
        "aarsmodell": aarsmodell,
        "drivstoff": DRIVSTOFF[(f >> 8) % len(DRIVSTOFF)],
        "girkasse": "Automat" if (f >> 12) % 2 else "Manuell",
        "kilometerstand": 12000 * alder + (f >> 16) % 20000,
        "farge": ["Svart", "Kvit", "Grå", "Sølv", "Raud"][(f >> 20) % 5],
        "eigar": "",
        "eu_kontroll_frist": f"{date.today().year + 1}-{1 + (f >> 24) % 12:02d}-28",
        "heftingar": [],
        "avgift_betalt_til": f"{date.today().year}-12-31",
        "vraakt": False,
        "stolen": False,
        "importert": bool((f >> 28) % 7 == 0),
        "eigarskifte_talet": 1 + (f >> 30) % 4,
    }


def omregistreringsavgift(bil: dict) -> int:
    """Estimat. Satsen er politikk og endrar seg — hentast frå Vegvesenet i drift.

    Vi viser eit tal fordi kjøparen må vite kva han skal ha på konto, og vi
    merkjer det tydeleg som estimat i grensesnittet.
    """
    alder = max(0, date.today().year - int(bil.get("aarsmodell", date.today().year)))
    if bil.get("drivstoff") == "Elektrisk":
        grunn = 1000
    elif alder < 3:
        grunn = 6600
    elif alder < 6:
        grunn = 4200
    elif alder < 10:
        grunn = 2600
    else:
        grunn = 1600
    return grunn


def hent(skilt: str) -> dict:
    """Alt appen veit om bilen. Kastar aldri — ukjende skilt gir demo-data."""
    kjend = skilt in DEMOREGISTER
    bil = dict(DEMOREGISTER[skilt]) if kjend else _dikta_bil(skilt)
    bil["skilt"] = skilt
    bil["kjelde"] = "demoregister" if kjend else "demo (dikta opp frå skiltet)"
    bil["omregistreringsavgift"] = omregistreringsavgift(bil)
    bil["merknader"] = åtvaringar(bil)
    return bil


def åtvaringar(bil: dict) -> list:
    """Det kjøparen bør vite før han signerer noko som helst."""
    ut = []
    if bil.get("stolen"):
        ut.append("Bilen er meld stolen. Ikkje gå vidare.")
    if bil.get("vraakt"):
        ut.append("Bilen er registrert vraka.")
    for h in bil.get("heftingar", []):
        ut.append(
            f"Heftelse: {h['långjevar']} har pant på {h['belop']:,} kr. "
            "Må slettast før eller samstundes med oppgjeret.".replace(",", " ")
        )
    if bil.get("importert"):
        ut.append("Bruktimportert — historikk før import er ikkje dekt av oppslaget.")
    if bil.get("eu_kontroll_frist", "") and bil["eu_kontroll_frist"] < str(date.today()):
        ut.append("Fristen for EU-kontroll er gått ut.")
    return ut


def heftingar_belop(bil: dict) -> int:
    return sum(int(h.get("belop", 0)) for h in bil.get("heftingar", []))
