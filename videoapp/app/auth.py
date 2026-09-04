"""Signerte token. Utan dette kan kven som helst bruke andre sine kredittar.

Vi lagar tokena sjølve med HMAC frå standardbiblioteket i staden for å
dra inn eit JWT-bibliotek. Grunnen er ikkje at JWT er dårleg, men at
dei fleste JWT-hòla kjem frå fleksibiliteten i formatet - `alg: none`,
algoritmeforveksling, valfrie felt som ikkje blir sjekka. Her finst det
berre éin algoritme, og han er ikkje eit felt nokon kan setje.

Tre reglar:

1. SAMANLIKN I KONSTANT TID. `==` på signaturar lek informasjon om kor
   mange teikn som stemte, og det er nok til å gjette seg fram over
   mange forsøk. `hmac.compare_digest` brukar same tid uansett.

2. TOKEN SKAL GÅ UT. Eit token utan utløp er eit passord som aldri kan
   trekkjast tilbake.

3. INGEN STANDARDNØKKEL. Startar appen med ein innebygd nøkkel, kjem
   han i produksjon før eller seinare, og då kan kven som helst som har
   lese koden lage gyldige token for kven som helst. Difor nektar vi å
   starte utan VIDEOAPP_TOKEN_NOKKEL.
"""

import base64
import hashlib
import hmac
import json
import os
import time

# Kor lenge eit token er gyldig. Kort nok til at eit lekka token blir
# verdilaust raskt, langt nok til at folk slepp å logge inn støtt.
LEVETID = 60 * 60 * 24 * 30

MIN_NOKKEL_LENGD = 32


class AuthFeil(Exception):
    """Token er ikkje gyldig. Aldri fortel kvifor - sjå _avvis()."""


def hent_nokkel(nokkel=None):
    """Nøkkelen frå miljøet. Kastar heller enn å finne på ein.

    Ein app som startar med ein svak standardnøkkel er verre enn ein
    som ikkje startar, fordi den første feilen oppdagar du ikkje.
    """
    n = nokkel or os.environ.get("VIDEOAPP_TOKEN_NOKKEL", "")
    if not n:
        raise AuthFeil(
            "VIDEOAPP_TOKEN_NOKKEL er ikkje sett. Lag ein med:\n"
            "  python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    if len(n) < MIN_NOKKEL_LENGD:
        raise AuthFeil(
            f"VIDEOAPP_TOKEN_NOKKEL er berre {len(n)} teikn. "
            f"Bruk minst {MIN_NOKKEL_LENGD}.")
    return n.encode("utf-8")


def _b64(raa):
    return base64.urlsafe_b64encode(raa).rstrip(b"=").decode("ascii")


def _av_b64(tekst):
    pad = "=" * (-len(tekst) % 4)
    return base64.urlsafe_b64decode(tekst + pad)


def lag_token(brukar, nokkel=None, levetid=LEVETID, no=None):
    """Lag eit token for ein brukar. Kall dette ved innlogging."""
    if not brukar:
        raise AuthFeil("Kan ikkje lage token utan brukar")
    no = time.time() if no is None else no
    kropp = _b64(json.dumps(
        {"b": str(brukar), "ut": int(no + levetid)},
        separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(hent_nokkel(nokkel), kropp.encode("ascii"),
                   hashlib.sha256).digest()
    return f"{kropp}.{_b64(sig)}"


def les_token(token, nokkel=None, no=None):
    """Returnerer brukar-id, eller kastar AuthFeil.

    Rekkjefølgja er viktig: vi sjekkar signaturen FØR vi tolkar
    innhaldet. Tolkar du først, køyrer du JSON-parsing på data ein
    angripar kontrollerer.
    """
    if not token or not isinstance(token, str):
        _avvis()
    bitar = token.split(".")
    if len(bitar) != 2:
        _avvis()
    kropp, sig = bitar

    try:
        venta = hmac.new(hent_nokkel(nokkel), kropp.encode("ascii"),
                         hashlib.sha256).digest()
        fekk = _av_b64(sig)
    except AuthFeil:
        raise
    except Exception:
        _avvis()

    # Konstant tid. Aldri `==` her.
    if not hmac.compare_digest(venta, fekk):
        _avvis()

    try:
        data = json.loads(_av_b64(kropp))
        brukar, utlop = data["b"], int(data["ut"])
    except Exception:
        _avvis()

    no = time.time() if no is None else no
    if no >= utlop:
        _avvis()
    if not brukar:
        _avvis()
    return brukar


def _avvis():
    """Alltid same feilmelding.

    Skil du mellom "utgått" og "feil signatur" utetter, fortel du ein
    angripar kva han skal justere. Logg gjerne detaljane internt.
    """
    raise AuthFeil("Ugyldig token")
