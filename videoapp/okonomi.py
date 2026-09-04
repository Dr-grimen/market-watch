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


def vis_brenn(p, brukarar, forsok):
    """Den største enkeltrisikoen i heile forretninga - viss du har gaave."""
    if p.gave_ved_registrering == 0:
        print("\nGRATISBRENN")
        linje()
        print("Ingen gratiskredittar. Ein registrering som aldri betaler")
        print("kostar deg null i generering.")
        return
    gratis = p.nivaa["rask"]
    lev = p.billegaste("rask")
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


def vis_abonnement(p, forsok):
    """Abonnement er RABATTEN, ikkje paalegget. Det er det som gir attendevending."""
    print(f"\nABONNEMENT   ({p.abo_pris:.0f} kr/mnd, {p.abo_kredittar} kredittar, "
          f"{p.abo_venta_bruk:.0%} av kvota blir brukt)")
    linje()
    if p.regenerering_kostar:
        print("Regenerering kostar kredittar -> kvota er eit HARDT tak paa")
        print("kva ein abonnent kan koste deg, uansett kor mykje han masar.")
    else:
        print("Regenerering er GRATIS -> ein kravstor brukar har ikkje tak.")
    linje()
    print(f"{'nivaa':<10} {'videoar':>8} {'kr/vid':>7} {'venta':>8} {'verste':>8} "
          f"{'v/2.5x':>8}")
    linje()
    for nokkel in p.nivaa:
        a = p.abonnement(nokkel, forsok=forsok)
        b = p.abonnement(nokkel, forsok=2.5)
        flagg = "" if a["verste_forteneste"] > 0 else "  <-- TAP"
        print(f"{nokkel:<10} {a['videoar']:>8.0f} {a['per_video']:>7.2f} "
              f"{a['venta_forteneste']:>+8.0f} {a['verste_forteneste']:>+8.0f} "
              f"{b['verste_forteneste']:>+8.0f}{flagg}")
    linje()
    a = p.abonnement("standard", forsok=forsok)
    print(f"Taaler ein kundeanskaffingskostnad paa {a['verste_forteneste']:.0f} kr")
    print("per maanad abonnenten blir verande - sjolv i verste fall.")


def vis_kva_prisen_baer(p, forsok):
    """Svaret paa 'kor mange videoar for X kroner'."""
    print("\nKVA EIN PRIS BER   (standardvideo, med marginkravet i konfigen)")
    linje()
    print(f"{'pris':>6} {'netto':>8} {'kredittar':>10} {'videoar':>9}")
    linje()
    per_video = p.pris_per_levert_video("standard", forsok=forsok)
    for pris in (49, 99, 149, 249, 399):
        n = p.kor_mange_videoar(pris, forsok=forsok, bruk=1.0)
        std = p.nivaa["standard"]
        print(f"{pris:>6.0f} {pris * (1 - p.app_store_kutt):>8.2f} "
              f"{n * std.kredittar:>10} {n:>9}")
    linje()
    print(f"Per levert standardvideo: {per_video:.2f} kr "
          f"(GPU + {p.faste_kroner_per_video:.2f} kr fast)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--forsok", type=float, default=1.3,
                    help="genereringar per levert video (standard 1.3)")
    ap.add_argument("--brukarar", type=int, default=5_000_000,
                    help="tal registreringar å rekne gratisbrenn for")
    ap.add_argument("--abonnement", type=float, default=0)
    args = ap.parse_args()

    p = Prisbok()
    print(f"\nValutakurs: {p.nok_per_usd} kr/USD   "
          f"Apple: {p.app_store_kutt:.0%}   "
          f"Faste per video: {p.faste_kroner_per_video} kr")

    vis_nivaa(p, args.forsok)
    vis_failover(p, args.forsok)
    vis_brenn(p, args.brukarar, args.forsok)
    vis_kva_prisen_baer(p, args.forsok)
    vis_abonnement(p, args.forsok)
    print("\nAlle tal frå config/providers.yaml. Endre der, ikkje her.\n")


if __name__ == "__main__":
    main()
