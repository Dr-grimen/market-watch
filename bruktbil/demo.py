#!/usr/bin/env python3
"""Køyrer heile handelen i terminalen, frå skilt til utbetaling.

Nyttig når du vil sjå at flyten heng saman utan å klikke deg gjennom appen:

    python3 demo.py
"""

import sys

from app import flyt, kontrakt
from app.modell import Rolle

SELJAR, KJOPAR = Rolle.SELJAR.value, Rolle.KJOPAR.value


def signer(h, rolle):
    okt = flyt.start_signering(h, rolle)
    flyt.fullfor_signering(h, rolle, kode=okt["kode"])
    print(f"  {h.part(rolle).namn} signerte (BankID {okt['ref']})")


def main() -> int:
    h = flyt.opprett_sal(
        skilt=sys.argv[1] if len(sys.argv) > 1 else "DB12345",
        pris=179000,
        namn="Ola Nordmann",
        fnr="01019000083",
        telefon="90000000",
        adresse="Storgata 1, 5000 Bergen",
        kontonummer="12345000001",
    )
    print(f"Sal oppretta: {h.bil['merke']} {h.bil['modell']} ({h.skilt})")
    for m in h.bil["merknader"]:
        print(f"  ⚠ {m}")
    print(f"  Delingskode til kjøparen: {h.kode}")

    flyt.bli_med(h, namn="Kari Nordmann", fnr="02029000002", adresse="Vegen 2, 5000 Bergen")
    flyt.set_vilkaar(h, SELJAR, utstyr="To nøklar, sommardekk", kjende_feil="Ripe i lakken bak")
    flyt.send_til_signering(h, SELJAR)
    signer(h, SELJAR)
    signer(h, KJOPAR)

    flyt.opprett_betaling(h, KJOPAR)
    print(f"  Kjøparen betaler inn {h.totalt_aa_betale} kr")
    flyt.stadfest_betaling(h)
    print(f"  Status på pengane: {h.betaling['status']}")

    flyt.send_salsmelding(h, SELJAR)
    flyt.stadfest_salsmelding(h, KJOPAR)
    print(f"  Eigarskifte: {h.eigarskifte['status']}")
    print(f"  Utbetaling: {h.betaling['status']} — {h.pris} kr til seljaren")
    print(f"\nSteg: {h.steg}\n")
    print(kontrakt.tekst(h))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
