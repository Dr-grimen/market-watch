"""Gyldige testdata. Kontrollsifra må stemme, elles stoppar valideringa oss."""

from app.modell import fodselsnummer_er_gyldig, kontonummer_er_gyldig


def gyldig_fnr(start: str = "01019") -> str:
    for n in range(0, 1000000):
        kandidat = f"{start}{n:06d}"[:11]
        if len(kandidat) == 11 and fodselsnummer_er_gyldig(kandidat):
            return kandidat
    raise AssertionError("fann ikkje gyldig fødselsnummer")


def gyldig_konto(start: str = "12345") -> str:
    for n in range(0, 1000000):
        kandidat = f"{start}{n:06d}"[:11]
        if len(kandidat) == 11 and kontonummer_er_gyldig(kandidat):
            return kandidat
    raise AssertionError("fann ikkje gyldig kontonummer")
