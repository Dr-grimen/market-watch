"""Sjekkar at målemotoren reknar rett.

Bakgrunnen: under ei analyse 27.08 laga eg eit engangsskript som viste at
ALLE "ned"-signala hadde +8 til +22 prosentpoeng kant i alle periodar.
Det såg fantastisk ut. Det var ein forteiknsfeil - eg inverterte ein
treffprosent som allereie peika rett veg.

Eg fanga det fordi tala var for gode og for like. Men eg burde ikkje
vere avhengig av magekjensle for å oppdage sånt, og eit slikt feil i
sjølve motoren ville vore usynleg: alle signal ville fått vekt, verktøyet
ville sendt sjølvsikre meldingar, og ingenting ville sagt ifrå.

Difor denne. Vi byggjer ein marknad der fasiten er kjend på førehand og
sjekkar at motoren finn nettopp det.

Bruk:  .venv/bin/python test_maaling.py
"""

import sys

from src import ensemble


def bygg_marknad(dagar=800, fall_kvar=7):
    """Ein marknad som fell kvar sjuande dag og stig alle andre."""
    bars = []
    kurs = 100.0
    for i in range(dagar):
        opning = kurs
        kurs = kurs * 0.98 if (i % fall_kvar == 0 and i > 0) else kurs * 1.01
        bars.append({
            "date": "01/%02d/%04d" % (i % 28 + 1, 2000 + i // 300),
            "open": opning,
            "high": max(opning, kurs) * 1.001,
            "low": min(opning, kurs) * 0.999,
            "close": kurs,
            "volume": 1e6,
        })
    return bars


def main():
    FALL_KVAR = 7
    bars = bygg_marknad(fall_kvar=FALL_KVAR)

    # Tre signal med kjend fasit.
    signals = [
        # Veit nøyaktig når fallet kjem. Skal ha 100 % treff.
        ("perfekt_ned", lambda i: "ned" if (i + 1) % FALL_KVAR == 0 and i > 0 else None),
        # Veit nøyaktig når det stig. Skal òg ha 100 %.
        ("perfekt_opp", lambda i: "opp" if (i + 1) % FALL_KVAR != 0 else None),
        # Slår ut på eit mønster som ikkje har noko med kursen å gjere.
        ("verdilaust", lambda i: "opp" if i % 3 == 0 else None),
    ]

    base, målt = ensemble.measure(bars, signals)
    feil = []

    forventa_base = (FALL_KVAR - 1) / float(FALL_KVAR)
    if abs(base - forventa_base) > 0.02:
        feil.append("basisraten er %.3f, skulle vore ~%.3f" % (base, forventa_base))

    ned = målt.get(("perfekt_ned", "ned"), {})
    if not ned.get("usable"):
        feil.append("perfekt_ned blei ikkje målt i det heile")
    else:
        if ned["rate"] < 0.99:
            feil.append("perfekt_ned traff %.1f %%, skulle vore 100" % (ned["rate"] * 100))
        # Fasiten for eit ned-signal er kor ofte det GÅR ned, ikkje opp.
        if abs(ned["base"] - (1 - forventa_base)) > 0.02:
            feil.append("perfekt_ned samanliknar mot %.3f, skulle vore %.3f "
                        "- FORTEIKNSFEIL" % (ned["base"], 1 - forventa_base))
        if ned["z"] < 5:
            feil.append("perfekt_ned fekk z=%.1f, skulle vore svært høg" % ned["z"])
        if not ned["weight"]:
            feil.append("perfekt_ned fekk vekt 0 - motoren forkastar eit ekte signal")

    opp = målt.get(("perfekt_opp", "opp"), {})
    if not opp.get("usable"):
        feil.append("perfekt_opp blei ikkje målt")
    elif opp["rate"] < 0.99:
        feil.append("perfekt_opp traff %.1f %%, skulle vore 100" % (opp["rate"] * 100))

    tull = målt.get(("verdilaust", "opp"), {})
    if tull.get("usable"):
        if abs(tull["rate"] - forventa_base) > 0.05:
            feil.append("verdilaust traff %.1f %%, skulle lege på basisraten"
                        % (tull["rate"] * 100))
        if tull["weight"]:
            feil.append("verdilaust fekk VEKT - motoren slepp gjennom støy")

    print("Måletest: marknad som fell kvar %d. dag\n" % FALL_KVAR)
    print("  %-14s %-4s %6s %8s %8s %8s" % ("signal", "seier", "n", "traff", "fasit", "z"))
    print("  " + "-" * 50)
    for (namn, retning), s in sorted(målt.items()):
        if not s.get("usable"):
            continue
        print("  %-14s %-4s %6d %7.1f%% %7.1f%% %+7.1f"
              % (namn, retning, s["n"], s["rate"] * 100, s["base"] * 100, s["z"]))

    print()
    if feil:
        print("FEIL I MÅLEMOTOREN:")
        for f in feil:
            print("  - %s" % f)
        return 1
    print("Alt stemmer. Motoren finn det ekte signalet og forkastar støyen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
