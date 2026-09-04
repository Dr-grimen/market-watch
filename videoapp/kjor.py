#!/usr/bin/env python3
"""Start tenesta. Dette er det du køyrer på serveren.

    python3 kjor.py              # API + ein arbeidar i same prosess
    python3 kjor.py --berre-api  # berre API-et
    python3 kjor.py --berre-arbeidar

I produksjon køyrer du dei kvar for seg: API-et bak ein lastbalanserar
med mange kopiar, og arbeidarane som eigne prosessar du kan skalere opp
og ned etter kølengda. Det er heile poenget med å ha delt dei.

Å køyre begge i same prosess er greitt for utvikling og for dei første
brukarane, men ikkje for lenge: ein arbeidar som held på i eitt minutt
stel tid frå API-et som skal svare på millisekund.
"""

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.api import lag_app
from app.arbeidar import Arbeidar, Bestilling
from app.deling import Deling
from app.ko import Ko
from app.ledger import Ledger
from app.moderering import Moderering
from app.oppsett import Oppsett, OppsettFeil
from app.pricing import Prisbok
from app.providers.minimax import MiniMax
from app.providers.router import Ruter

log = logging.getLogger("kjor")

DATA = Path(os.environ.get("VIDEOAPP_DATA", "data"))


def les_env_fil(sti=".env"):
    """Les .env om han finst. Miljøet vinn alltid over fila."""
    p = Path(sti)
    if not p.exists():
        return
    for linje in p.read_text(encoding="utf-8").splitlines():
        linje = linje.strip()
        if not linje or linje.startswith("#") or "=" not in linje:
            continue
        nokkel, verdi = linje.split("=", 1)
        os.environ.setdefault(nokkel.strip(), verdi.strip())


def bygg(oppsett, prisbok):
    """Set saman alle delane. Éin stad, så det er lett å sjå kva som heng i kva."""
    DATA.mkdir(parents=True, exist_ok=True)

    if oppsett.er_produksjon():
        # Mønsteret i ledger og kø er alt rett (BEGIN IMMEDIATE blir
        # SELECT ... FOR UPDATE), men portinga er ikkje gjord.
        raise OppsettFeil(
            "DATABASE_URL er sett, men Postgres-støtte er ikkje implementert "
            "enno. Fjern DATABASE_URL for å køyre på SQLite, eller port "
            "Ledger og Ko først. Ikkje køyr SQLite i produksjon med fleire "
            "prosessar - dei vil låse kvarandre ut.")

    ledger = Ledger(str(DATA / "ledger.db"))
    ko = Ko(str(DATA / "ko.db"))
    deling = Deling(ledger, prisbok, str(DATA / "deling.db"))
    moderering = Moderering(api_nokkel=oppsett.anthropic_nokkel,
                            logg_sti=DATA / "moderering.jsonl")

    adaptere = {}
    for namn, lev in prisbok.leverandorar.items():
        nokkel = oppsett.leverandor_nokkel.get(namn)
        if not nokkel or not lev.aktiv:
            continue
        if namn.startswith("minimax"):
            modell = ("MiniMax-Hailuo-02" if "02" in namn
                      else "MiniMax-Hailuo-02-Fast")
            adaptere[namn] = MiniMax(lev, api_nokkel=nokkel, modell=modell)
        # Seedance og Runway manglar adapter. Dei er i prislista, men
        # utan adapter blir dei aldri valde - ruteren hoppar over dei.

    ruter = Ruter(prisbok, adaptere)
    bestilling = Bestilling(ko, ledger, prisbok, moderering)
    return ledger, ko, deling, ruter, bestilling


def arbeidarsloyfe(arbeidar, ledger, stopp, kvil=2.0):
    """Køyr jobbar til nokon seier stopp.

    Ryddar gamle reservasjonar med jamne mellomrom. Utan det blir
    kredittar hengande når ein arbeidar kræsjar midt i ein jobb.
    """
    sist_rydda = 0.0
    while not stopp.is_set():
        try:
            if arbeidar.koyr_ein() is None:
                stopp.wait(kvil)
        except Exception:                            # noqa: BLE001
            # Ein arbeidar som dør stille er verre enn ein som loggar
            # og held fram. Jobben blir lagd ut att av køen uansett.
            log.exception("Arbeidaren feila på ein jobb")
            stopp.wait(kvil)

        if time.time() - sist_rydda > 300:
            sist_rydda = time.time()
            try:
                n = ledger.rydd_gamle_reservasjonar()
                if n:
                    log.warning("Rydda %s fastlåste reservasjonar", n)
            except Exception:                        # noqa: BLE001
                log.exception("Rydding feila")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--berre-api", action="store_true")
    ap.add_argument("--berre-arbeidar", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--vert", default="127.0.0.1")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")

    les_env_fil()
    prisbok = Prisbok()
    oppsett = Oppsett.frae_miljoet()

    try:
        oppsett.sjekk(prisbok)
    except OppsettFeil as e:
        print(f"\n{e}\n", file=sys.stderr)
        return 1

    for aatvaring in oppsett.manglar(prisbok):
        log.warning(aatvaring.replace("ÅTVARING: ", ""))

    ledger, ko, deling, ruter, bestilling = bygg(oppsett, prisbok)

    if not ruter.adaptere:
        print("\nIngen leverandør har både nøkkel og adapter. "
              "Sjå bygg() i denne fila.\n", file=sys.stderr)
        return 1
    log.info("Leverandørar klare: %s", ", ".join(sorted(ruter.adaptere)))

    stopp = threading.Event()
    traad = None

    if not args.berre_api:
        arbeidar = Arbeidar(ko, ledger, ruter, prisbok,
                            namn=f"arbeidar-{os.getpid()}",
                            anthropic_nokkel=oppsett.anthropic_nokkel)
        traad = threading.Thread(
            target=arbeidarsloyfe, args=(arbeidar, ledger, stopp), daemon=True)
        traad.start()
        log.info("Arbeidar i gang")

    if args.berre_arbeidar:
        log.info("Køyrer utan API. Ctrl-C for å stoppe.")
        try:
            while traad and traad.is_alive():
                traad.join(1)
        except KeyboardInterrupt:
            pass
        stopp.set()
        return 0

    import uvicorn
    app = lag_app(bestilling, ko, ledger, prisbok,
                  token_nokkel=oppsett.token_nokkel)
    log.info("API på http://%s:%s", args.vert, args.port)
    try:
        uvicorn.run(app, host=args.vert, port=args.port, log_level="warning")
    finally:
        stopp.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
