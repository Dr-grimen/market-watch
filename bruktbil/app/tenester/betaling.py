"""Oppgjer over klientkonto.

Poenget med appen: kjøparen sine pengar skal stå trygt medan bilen skiftar
eigar. Pengane går inn på ein klientkonto, blir ståande til eigarskiftet er
gjennomført hos Vegvesenet, og først då blir dei betalte ut til seljaren.

I produksjon er dette ein avtale med bank eller betalingsføretak, med
klientmiddelkonto, kvitvaskingskontroll og rekneskapsplikt. Her er det ei
ordbok i minnet, men grensesnittet er det same som vi vil ha mot banken:
opprett -> stadfest innbetaling -> frigi (eller refunder).
"""

from __future__ import annotations

import secrets

from ..modell import Feil, no_tid

VENTAR = "ventar_innbetaling"
PAA_KLIENTKONTO = "paa_klientkonto"
UTBETALT = "utbetalt"
REFUNDERT = "refundert"

_BETALINGAR: dict[str, dict] = {}


def opprett(belop: int, gebyr: int, referanse: str, til_konto: str) -> dict:
    if belop <= 0:
        raise Feil("Beløpet må vere over null.")
    bid = "pay_" + secrets.token_hex(6)
    betaling = {
        "id": bid,
        "belop": belop,
        "gebyr": gebyr,
        "referanse": referanse,
        "til_konto": til_konto,
        "klientkonto": "1506.21.00000",
        "status": VENTAR,
        "oppretta": no_tid(),
        "innbetalt": "",
        "utbetalt": "",
    }
    _BETALINGAR[bid] = betaling
    return dict(betaling)


def hent(bid: str) -> dict:
    if bid not in _BETALINGAR:
        raise Feil("Ukjend betaling.")
    return dict(_BETALINGAR[bid])


def stadfest_innbetaling(bid: str) -> dict:
    """Banken melder at pengane er komne inn. I drift er dette eit webhook."""
    b = _BETALINGAR.get(bid)
    if not b:
        raise Feil("Ukjend betaling.")
    if b["status"] != VENTAR:
        raise Feil("Betalinga er allereie registrert.")
    b["status"] = PAA_KLIENTKONTO
    b["innbetalt"] = no_tid()
    return dict(b)


def frigi(bid: str) -> dict:
    """Pengane til seljaren. Skal berre kallast etter fullført eigarskifte."""
    b = _BETALINGAR.get(bid)
    if not b:
        raise Feil("Ukjend betaling.")
    if b["status"] != PAA_KLIENTKONTO:
        raise Feil("Pengane står ikkje på klientkonto.")
    b["status"] = UTBETALT
    b["utbetalt"] = no_tid()
    return dict(b)


def refunder(bid: str) -> dict:
    """Handelen sprakk. Kjøparen får pengane tilbake, gebyret òg."""
    b = _BETALINGAR.get(bid)
    if not b:
        raise Feil("Ukjend betaling.")
    if b["status"] not in (VENTAR, PAA_KLIENTKONTO):
        raise Feil("Betalinga kan ikkje refunderast no.")
    b["status"] = REFUNDERT
    return dict(b)


def nullstill() -> None:
    """Berre for testar."""
    _BETALINGAR.clear()
