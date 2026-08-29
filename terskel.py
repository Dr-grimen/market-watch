"""Kva ville ULIKE terskelar gitt?

Simuleringa kostar 65 Claude-kall. Denne kostar ingenting: ho les
rådataa frå simulering.json og reknar ut kva som ville skjedd ved kvar
mogleg terskel. Slik kan valet takast med tal på bordet i staden for ei
kjensle, og utan å betale på nytt for kvart forsøk.

Tre tal betyr noko, og dei trekkjer i kvar si retning:

  KOR MANGE meldingar. Eit verktøy som seier noko to gonger i året
  hjelper ingen, same kor rett det har.

  KOR OFTE RETT. Under basisraten er verktøyet verre enn å gjette.

  Z. Om skilnaden frå eit myntkast er noko anna enn flaks. Med få
  meldingar er svaret nesten alltid nei, uansett kor pen prosenten ser
  ut - og det er nettopp difor talet står her.

Bruk:  .venv/bin/python terskel.py
"""

import json
import math
import os
import sys


def main():
    if not os.path.exists("simulering.json"):
        print("simulering.json manglar. Køyr simuler.py fyrst.")
        return 1

    with open("simulering.json", "r", encoding="utf-8") as fh:
        res = json.load(fh)

    dagar = len(res)
    opp_dagar = sum(1 for r in res if r["faktisk"] > 0)
    basis = opp_dagar / float(dagar) if dagar else 0.5

    print("Simulering: %d handledagar. Basisrate %.0f %% opp-dagar.\n"
          % (dagar, basis * 100))

    retningar = [r for r in res if r["retning"] in ("opp", "ned")]
    if retningar:
        conf = sorted(r["conf"] for r in retningar)
        print("  Modellen gav retning på %d av %d dagar." % (len(retningar), dagar))
        print("  Confidence: lågast %.0f %%, median %.0f %%, høgast %.0f %%\n"
              % (conf[0] * 100, conf[len(conf) // 2] * 100, conf[-1] * 100))
    else:
        print("  Modellen gav aldri ei retning. Ingen terskel hjelper.\n")
        return 0

    print("  %-9s %8s %10s %9s %8s %9s"
          % ("terskel", "meldingar", "per mnd", "rett", "z", "snitt"))
    print("  " + "-" * 60)

    for terskel in (0.40, 0.45, 0.50, 0.52, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70):
        sendt = [r for r in retningar if r["conf"] >= terskel]
        if not sendt:
            print("  %6.0f %%   %8d" % (terskel * 100, 0))
            continue

        traff = sum(1 for r in sendt
                    if (r["retning"] == "opp" and r["faktisk"] > 0)
                    or (r["retning"] == "ned" and r["faktisk"] < 0))
        andel = traff / float(len(sendt))
        per_mnd = len(sendt) / (dagar / 21.0)
        avk = sum(r["faktisk"] if r["retning"] == "opp" else -r["faktisk"]
                  for r in sendt) / len(sendt)
        se = math.sqrt(0.25 / len(sendt))
        z = (andel - 0.5) / se if se else 0.0

        merke = ""
        if len(sendt) >= 10 and z >= 2:
            merke = "  <- ekte"
        elif len(sendt) < 5:
            merke = "  (for få)"

        print("  %6.0f %%   %8d %9.1f %8.0f %% %+8.1f %+8.2f %%%s"
              % (terskel * 100, len(sendt), per_mnd, andel * 100, z, avk, merke))

    print("\n  'rett' må slå basisraten på %.0f %% for at retninga skal vere"
          % (basis * 100))
    print("  verdt noko. Og med under ti meldingar seier z ingenting - då")
    print("  er talet ein observasjon, ikkje eit funn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
