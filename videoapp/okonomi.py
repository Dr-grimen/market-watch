#!/usr/bin/env python3
"""Kva denne appen tener og brenn. Køyr han før du endrar ein pris.

    python3 okonomi.py
    python3 okonomi.py --forsok 2.5 --brukarar 1000000

Alle tal kjem frå config/providers.yaml. Endrar du ein pris der,
endrar dette seg. Ingen tal er skrivne inn her.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.pricing import Prisbok


def linje(tegn="-", n=68):
    print(tegn * n)


def vis_nivaa(p, forsok):
    print(f"\nMARGIN PER VIDEO   (regenerering: {forsok}x per levert video)")
    linje()
    print(f"{'nivå':<10} {'leverandør':<20} {'pris':>6} {'gpu':>7} "
          f"{'netto':>7} {'margin':>8}")
    linje()
    for nokkel in p.nivaa:
        m = p.margin(nokkel, forsok=forsok)
        flagg = "" if m.margin >= p.minste_margin else "  <-- for lågt"
        print(f"{nokkel:<10} {m.leverandor:<20} {m.inntekt_brutto:>6.0f} "
              f"{m.gpu_kostnad:>7.2f} {m.bruttofortenest:>7.2f} "
              f"{m.margin:>7.1%}{flagg}")


def vis_failover(p, forsok):
    print("\nFAILOVER   (held marginen om den billege er nede?)")
    linje()
    for nokkel in p.nivaa:
        kand = p.kandidatar(nokkel)
        if len(kand) < 2:
            print(f"{nokkel:<10} BERRE {len(kand)} leverandør - ingen failover")
            continue
        verst = max(kand, key=lambda l: l.usd_per_second)
        m = p.margin(nokkel, verst.nokkel, forsok=forsok)
        print(f"{nokkel:<10} {len(kand)} kandidatar, verste fall "
              f"{verst.nokkel:<20} {m.margin:>6.1%}")


def vis_gratisbrenn(p, brukarar, forsok):
    """Den største enkeltrisikoen i heile forretninga."""
    gratis = p.nivaa["gratis"]
    lev = p.billegaste("gratis")
    per_video = lev.kostnad_nok(gratis.sekund, p.nok_per_usd) * forsok
    videoar = p.gave_ved_registrering // gratis.kredittar
    per_brukar = per_video * videoar

    print(f"\nGRATISBRENN   ({p.gave_ved_registrering} kredittar = "
          f"{videoar} videoar per ny brukar)")
    linje()
    print(f"Kostnad per ny brukar som aldri betaler: {per_brukar:.2f} kr")
    linje()
    for n in (10_000, 100_000, 1_000_000, brukarar):
        print(f"{n:>12,} registreringar  ->  {n * per_brukar:>14,.0f} kr ut døra"
              .replace(",", " "))


def vis_abonnement(p, forsok, pris=149, kredittar=400, bruk=0.6):
    """Abonnement er RABATTEN, ikkje påslaget. Det er det som gir attendevending."""
    standard = p.nivaa["standard"]
    lev = p.billegaste("standard")
    per_video = lev.kostnad_nok(standard.sekund, p.nok_per_usd) * forsok

    netto = pris * (1 - p.app_store_kutt)
    brukte = kredittar * bruk
    videoar = brukte / standard.kredittar
    kostnad = videoar * (per_video + p.faste_kroner_per_video)
    forteneste = netto - kostnad

    print(f"\nABONNEMENT   ({pris} kr/mnd, {kredittar} kredittar, "
          f"{bruk:.0%} blir brukt)")
    linje()
    print(f"  Netto etter Apple ({p.app_store_kutt:.0%}):  {netto:>8.2f} kr")
    print(f"  Brukar {videoar:.0f} videoar:            {-kostnad:>8.2f} kr")
    print(f"  = forteneste per abonnent:   {forteneste:>8.2f} kr "
          f"({forteneste / netto:.0%})")
    print(f"\n  Kredittar som forfell ubrukte: {kredittar * (1 - bruk):.0f} "
          f"({1 - bruk:.0%}) - dette er rein margin.")
    if forteneste > 0:
        print(f"  Tåler ein kundeanskaffingskostnad på {forteneste:.0f} kr "
              "per månad abonnenten blir verande.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--forsok", type=float, default=1.3,
                    help="genereringar per levert video (standard 1.3)")
    ap.add_argument("--brukarar", type=int, default=5_000_000,
                    help="tal registreringar å rekne gratisbrenn for")
    ap.add_argument("--abonnement", type=float, default=149)
    args = ap.parse_args()

    p = Prisbok()
    print(f"\nValutakurs: {p.nok_per_usd} kr/USD   "
          f"Apple: {p.app_store_kutt:.0%}   "
          f"Faste per video: {p.faste_kroner_per_video} kr")

    vis_nivaa(p, args.forsok)
    vis_failover(p, args.forsok)
    vis_gratisbrenn(p, args.brukarar, args.forsok)
    vis_abonnement(p, args.forsok, pris=args.abonnement)
    print("\nAlle tal frå config/providers.yaml. Endre der, ikkje her.\n")


if __name__ == "__main__":
    main()
