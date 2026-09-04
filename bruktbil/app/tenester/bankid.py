"""Signering med BankID.

I produksjon går dette gjennom ein signeringsleverandør (Signicat, Vipps
BankID eller Criipto): vi sender dokumentet, brukaren autentiserer seg i
BankID-appen, og vi får tilbake ein signert PDF med sertifikatkjede som held
i retten.

Her simulerer vi det: `start` gir ein referanse og ein eingongskode, `stadfest`
godtek berre rett kode til referansen. Koden er utleidd frå referansen slik at
demoen kan vise han på skjermen — ein ekte BankID-kode kjem sjølvsagt aldri
frå vår server.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ..modell import Feil, fodselsnummer_er_gyldig, no_tid

_HEMMELEG = b"demo-bankid"


def _kode(ref: str) -> str:
    sum_ = hmac.new(_HEMMELEG, ref.encode(), hashlib.sha256).hexdigest()
    return f"{int(sum_[:8], 16) % 1000000:06d}"


def identifiser(fnr: str, namn: str) -> dict:
    """Innlogginga. Skjer før kontrakten blir laga, ikkje midt i signeringa.

    Det er ikkje ein detalj: kontrakten inneheld namn og fødselsnummer, og han
    må stå heilt stille frå den første signaturen til den andre. Difor kjenner
    vi partane før teksten blir skriven.
    """
    if not fodselsnummer_er_gyldig(fnr):
        raise Feil("Fødselsnummeret er ikkje gyldig (kontrollsifra stemmer ikkje).")
    if not namn.strip():
        raise Feil("Namn manglar.")
    return {"namn": namn.strip(), "tid": no_tid(), "metode": "BankID (demo)"}


def start(dokument_hash: str, namn: str) -> dict:
    """Startar ei signeringsøkt. Returnerer ref + koden demoen skal vise."""
    if not namn.strip():
        raise Feil("Namn manglar.")
    ref = "bid_" + secrets.token_hex(8)
    return {
        "ref": ref,
        "kode": _kode(ref),
        "dokument": dokument_hash,
        "starta": no_tid(),
    }


def stadfest(ref: str, kode: str) -> dict:
    """Godkjenner signeringa. Returnerer kvitteringa vi lagrar på handelen."""
    if not hmac.compare_digest(_kode(ref), (kode or "").strip()):
        raise Feil("Feil kode. Prøv igjen.")
    return {
        "ref": ref,
        "tid": no_tid(),
        "metode": "BankID (demo)",
    }
