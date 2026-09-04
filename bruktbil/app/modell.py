"""Datamodellen for éin bruktbilhandel.

Ein handel er eitt objekt som lever frå seljaren skriv inn skiltnummeret til
pengane står på kontoen hans og bilen står i kjøparen sitt namn. Alt som skjer
undervegs heng på dette objektet, slik at begge partar ser same sanninga.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

GEBYR_KRONER = 199
"""Det appen kostar. Eitt tal, éin gong, betalt av kjøparen ved oppgjer."""


class Steg(str, Enum):
    """Kvar i handelen partane er. Rekkjefølgja er meininga med klassen."""

    VENTAR_KJOPAR = "ventar_kjopar"
    VILKAAR = "vilkaar"
    SIGNERING = "signering"
    BETALING = "betaling"
    EIGARSKIFTE = "eigarskifte"
    FULLFORT = "fullfort"
    AVBROTEN = "avbroten"


REKKJEFOLGJE = [
    Steg.VENTAR_KJOPAR,
    Steg.VILKAAR,
    Steg.SIGNERING,
    Steg.BETALING,
    Steg.EIGARSKIFTE,
    Steg.FULLFORT,
]

STEGNAMN = {
    Steg.VENTAR_KJOPAR: "Ventar på kjøpar",
    Steg.VILKAAR: "Vilkår",
    Steg.SIGNERING: "Signering",
    Steg.BETALING: "Betaling",
    Steg.EIGARSKIFTE: "Eigarskifte",
    Steg.FULLFORT: "Fullført",
    Steg.AVBROTEN: "Avbroten",
}


class Rolle(str, Enum):
    SELJAR = "seljar"
    KJOPAR = "kjopar"


class Feil(Exception):
    """Noko partane gjorde er ikkje lov no. Meldinga skal kunne visast rått."""


# --- validering ------------------------------------------------------------

SKILT = re.compile(r"^[A-ZÆØÅ]{2}\s?\d{4,5}$")


def normaliser_skilt(raatekst: str) -> str:
    """'db 12345' -> 'DB12345'. Kastar Feil om det ikkje liknar eit skilt."""
    skilt = (raatekst or "").upper().replace(" ", "").replace("-", "").strip()
    if not SKILT.match(skilt):
        raise Feil(f"«{raatekst}" + "» ser ikkje ut som eit norsk skiltnummer.")
    return skilt


def fodselsnummer_er_gyldig(fnr: str) -> bool:
    """Ekte mod11-kontroll. Slurvete siffer skal stoppe her, ikkje hos BankID."""
    fnr = (fnr or "").replace(" ", "")
    if not re.fullmatch(r"\d{11}", fnr):
        return False
    vekt1 = [3, 7, 6, 1, 8, 9, 4, 5, 2]
    vekt2 = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    siffer = [int(t) for t in fnr]
    for vekt, plass in ((vekt1, 9), (vekt2, 10)):
        rest = sum(v * s for v, s in zip(vekt, siffer)) % 11
        kontroll = 0 if rest == 0 else 11 - rest
        if kontroll == 10 or kontroll != siffer[plass]:
            return False
    return True


def maskert(fnr: str) -> str:
    """Vi lagrar aldri heile fødselsnummeret i klartekst i handelen."""
    fnr = (fnr or "").replace(" ", "")
    return f"{fnr[:6]}*****" if len(fnr) == 11 else "***********"


def kontonummer_er_gyldig(konto: str) -> bool:
    """Norsk 11-sifra kontonummer med mod11-kontrollsiffer."""
    konto = re.sub(r"[.\s]", "", konto or "")
    if not re.fullmatch(r"\d{11}", konto):
        return False
    vekter = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    rest = sum(v * int(s) for v, s in zip(vekter, konto)) % 11
    kontroll = 0 if rest == 0 else 11 - rest
    return kontroll != 10 and kontroll == int(konto[10])


def no_tid() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- delane av ein handel --------------------------------------------------


@dataclass
class Part:
    """Ein av dei to. Kjøparen finst ikkje før nokon har brukt delingskoden."""

    rolle: str
    namn: str = ""
    telefon: str = ""
    epost: str = ""
    fnr_maskert: str = ""
    adresse: str = ""
    kontonummer: str = ""
    token: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    signert: str = ""  # tidspunkt, tom streng til han har signert
    signatur_ref: str = ""

    @property
    def er_med(self) -> bool:
        return bool(self.namn)


@dataclass
class Hending:
    tid: str
    tekst: str
    rolle: str = ""


@dataclass
class Handel:
    id: str
    kode: str
    oppretta: str
    steg: str = Steg.VENTAR_KJOPAR.value
    skilt: str = ""
    bil: dict = field(default_factory=dict)
    pris: int = 0
    vilkaar: dict = field(default_factory=dict)
    seljar: Part = field(default_factory=lambda: Part(Rolle.SELJAR.value))
    kjopar: Part = field(default_factory=lambda: Part(Rolle.KJOPAR.value))
    kontrakt_signatur: str = ""  # hash av kontrakten slik han var ved signering
    betaling: dict = field(default_factory=dict)
    eigarskifte: dict = field(default_factory=dict)
    forsikring: dict = field(default_factory=dict)
    laan: dict = field(default_factory=dict)
    logg: list = field(default_factory=list)

    # -- oppslag -----------------------------------------------------------

    def part(self, rolle: str) -> Part:
        if rolle == Rolle.SELJAR.value:
            return self.seljar
        if rolle == Rolle.KJOPAR.value:
            return self.kjopar
        raise Feil(f"Ukjend rolle: {rolle}")

    def motpart(self, rolle: str) -> Part:
        annan = Rolle.KJOPAR if rolle == Rolle.SELJAR.value else Rolle.SELJAR
        return self.part(annan.value)

    @property
    def begge_har_signert(self) -> bool:
        return bool(self.seljar.signert and self.kjopar.signert)

    @property
    def totalt_aa_betale(self) -> int:
        """Det kjøparen sender inn: bilen + omregistrering + vårt gebyr."""
        return self.pris + self.omregistreringsavgift + GEBYR_KRONER

    @property
    def omregistreringsavgift(self) -> int:
        return int(self.bil.get("omregistreringsavgift", 0))

    def noter(self, tekst: str, rolle: str = "") -> None:
        self.logg.append(asdict(Hending(no_tid(), tekst, rolle)))

    # -- lagring -----------------------------------------------------------

    def til_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def frå_dict(cls, d: dict) -> "Handel":
        d = dict(d)
        d["seljar"] = Part(**d.get("seljar", {"rolle": Rolle.SELJAR.value}))
        d["kjopar"] = Part(**d.get("kjopar", {"rolle": Rolle.KJOPAR.value}))
        return cls(**d)


def ny_handel() -> Handel:
    return Handel(
        id=secrets.token_urlsafe(9),
        kode=delingskode(),
        oppretta=no_tid(),
    )


def delingskode() -> str:
    """Seks teikn kjøparen kan lese opp på telefon. Utan I, O, 0 og 1."""
    alfabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabet) for _ in range(6))


def kort_hash(tekst: str) -> str:
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()[:16]


def klokke() -> float:
    return time.time()
