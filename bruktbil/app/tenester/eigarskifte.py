"""Salsmelding og omregistrering hos Statens vegvesen.

Slik det verkeleg fungerer: seljaren sender salsmelding, kjøparen stadfestar
ho, og omregistreringa skjer når avgifta er betalt. Begge partar må vere med —
difor er dette to steg her òg.

I produksjon krev dette integrasjon mot Vegvesenet sine tenester og at partane
er autentiserte med BankID. Her er det ei ordbok med same stegvise oppførsel.
"""

from __future__ import annotations

import secrets

from ..modell import Feil, no_tid

MELD = "meld"
STADFESTA = "stadfesta"
FULLFORT = "fullfort"

_SAKER: dict[str, dict] = {}


def send_salsmelding(skilt: str, seljar: str, kjopar: str, pris: int) -> dict:
    sid = "eig_" + secrets.token_hex(6)
    sak = {
        "id": sid,
        "skilt": skilt,
        "seljar": seljar,
        "kjopar": kjopar,
        "pris": pris,
        "status": MELD,
        "meld": no_tid(),
        "stadfesta": "",
        "fullfort": "",
    }
    _SAKER[sid] = sak
    return dict(sak)


def stadfest(sid: str) -> dict:
    """Kjøparen stadfestar salsmeldinga i sin eigen innboks hos Vegvesenet."""
    sak = _SAKER.get(sid)
    if not sak:
        raise Feil("Ukjend salsmelding.")
    if sak["status"] != MELD:
        raise Feil("Salsmeldinga er allereie stadfesta.")
    sak["status"] = STADFESTA
    sak["stadfesta"] = no_tid()
    return dict(sak)


def fullfor(sid: str) -> dict:
    """Omregistreringa er gjennomført — bilen står i kjøparen sitt namn."""
    sak = _SAKER.get(sid)
    if not sak:
        raise Feil("Ukjend salsmelding.")
    if sak["status"] != STADFESTA:
        raise Feil("Kjøparen har ikkje stadfesta salsmeldinga enno.")
    sak["status"] = FULLFORT
    sak["fullfort"] = no_tid()
    return dict(sak)


def hent(sid: str) -> dict:
    if sid not in _SAKER:
        raise Feil("Ukjend salsmelding.")
    return dict(_SAKER[sid])


def nullstill() -> None:
    _SAKER.clear()
