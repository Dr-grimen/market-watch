"""Er modellen sikker naar han BOER vere sikker?

Dette er den strengaste testen verktoeyet har. Han svarer paa spoersmaalet
Sondre stilte: "sjekk om dei er sikre nokk da".

Metoden bruker at kalenderen har HISTORISKE tal med baade faktisk verdi og
konsensus. Vi finn dagar der eit stort tal bomma, gir modellen nøyaktig det
materialet han ville hatt den dagen - kalenderen slik han saag ut, chartet
kutta der - og samanliknar det han sa med det som faktisk hende.

Resultat 28.08.2026, 64 hendingsdagar over to aar:

    han sa 50-60 %   ->  hadde rett 50 %   (paastod 57 %)
    han sa 60-66 %   ->  hadde rett 62 %   (paastod 62 %)  godt kalibrert
    han sa 66-75 %   ->  hadde rett 44 %   (paastod 70 %)  25 poeng for hoegt

    Over terskelen paa 66 %: 18 meldingar, 8 rett = 44 %. z=-0,5.

Konklusjonen er ikkje at han er litt overkonfident. Han er at det ikkje
finst maalt evidens for at retningsvurderinga slaar eit myntkast - paa
noko konfidensnivaa. Og mest talande: bootta 60-66 % var noeyaktig
kalibrert, medan bootta over 66 % var verst. Terskelen vaar plukkar altsaa
ut nettopp det omraadet der modellen er minst paalitelege.

Ei viktig avgrensing: testen gir modellen berre kalendertalet, ikkje dei
tolv nyheitssakene han faar i produksjon. Han kan gjere det betre med meir
kontekst. Men retninga stemmer med alt anna som er maalt - 50 % paa 60
tekniske dagar, og "opp" paa 13 av 14 krakk-dagar.

Bruk:  .venv/bin/python kalibrer_hendingar.py
"""

import concurrent.futures
import json
import math
import re
import sys
from datetime import date, timedelta

from src.config import load_config, env
from src.sources import history, calendar as cal
from src import analyze, technicals as T

VIKTIGE = ("core cpi", "cpi", "core pce", "pce", "nonfarm payrolls",
           "unemployment rate", "ppi", "core ppi")
MIN_AVVIK = 0.15


def _tal(tekst):
    m = re.search(r"-?\d+\.?\d*", (tekst or "").replace(",", ""))
    return float(m.group()) if m else None


def finn_bommar(frå_år=2024, frå_mnd=9):
    """Dagar der eit tungt tal bomma paa konsensus."""
    # Alle kvardagar, ikkje eit utval. Fyrste versjonen skanna sju dagar
    # per maanad og fann 30 hendingar - for lite til aa seie noko. Med
    # alle kvardagar blir utvalet stort nok til at tala betyr noko.
    datoar = []
    d = date(frå_år, frå_mnd, 1)
    i_dag = date.today()
    while d < i_dag - timedelta(days=3):
        if d.weekday() < 5:
            datoar.append(d.isoformat())
        d += timedelta(days=1)

    def sjekk(dato):
        ut = []
        for e in cal.fetch_economic(dato):
            if e["name"].lower().strip() not in VIKTIGE:
                continue
            a, k = _tal(e["actual"]), _tal(e["consensus"])
            if a is None or k is None or abs(a - k) < MIN_AVVIK:
                continue
            ut.append({"dato": dato, "namn": e["name"], "faktisk": e["actual"],
                       "venta": e["consensus"], "avvik": a - k})
        return ut

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        alle = [x for grp in pool.map(sjekk, datoar) for x in grp]

    # Éin per dato - den med størst avvik.
    per_dato = {}
    for x in alle:
        d = x["dato"]
        if d not in per_dato or abs(x["avvik"]) > abs(per_dato[d]["avvik"]):
            per_dato[d] = x
    return list(per_dato.values())


def main():
    load_config()
    nøkkel = env("ANTHROPIC_API_KEY")
    if not nøkkel:
        print("ANTHROPIC_API_KEY manglar.")
        return 1
    terskel = load_config()["confidence_threshold"]

    bars = history.fetch_daily("QQQ")
    closes = [b["close"] for b in bars]
    indeks = {}
    for i, bar in enumerate(bars):
        p = bar["date"].split("/")
        indeks["%s-%s-%s" % (p[2], p[0], p[1])] = i

    hendingar = [x for x in finn_bommar()
                 if x["dato"] in indeks
                 and indeks[x["dato"]] > T.WARMUP
                 and indeks[x["dato"]] + 1 < len(closes)]
    print("Testar %d hendingsdagar.\n" % len(hendingar))

    def ein(x):
        i = indeks[x["dato"]]
        try:
            rapport = T.analyse(bars[:i + 1], "QQQ (Nasdaq-100)")
            verdict = analyze.evaluate(
                [{"source": "BLS", "tier": "primary", "age_hours": 0.3,
                  "source_count": 6,
                  "title": "%s kom inn på %s mot venta %s"
                           % (x["namn"], x["faktisk"], x["venta"])}],
                "NASDAQ 100 (siste slutt %.2f)" % closes[i],
                api_key=nøkkel,
                calendar_summary=cal.format_calendar(cal.fetch_today(x["dato"])),
                technical_summary=T.format_report(rapport) if rapport else "")
            if not verdict:
                return None
            return (verdict["direction"], verdict["confidence"],
                    (closes[i + 1] / closes[i] - 1) * 100)
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        res = [r for r in pool.map(ein, hendingar) if r]

    if not res:
        print("Ingen svar kom gjennom.")
        return 1

    def rett(d, endring):
        return (d == "opp" and endring > 0) or (d == "ned" and endring < 0)

    print("  %-12s %5s %8s %10s" % ("conf-bøtte", "n", "traff", "påstand"))
    print("  " + "-" * 42)
    for lo, hi in ((0, 0.5), (0.5, 0.6), (0.6, 0.66), (0.66, 0.75), (0.75, 1.01)):
        bøtte = [r for r in res if lo <= r[1] < hi and r[0] in ("opp", "ned")]
        if not bøtte:
            continue
        traff = sum(1 for d, _, f in bøtte if rett(d, f))
        påstand = sum(c for _, c, _ in bøtte) / len(bøtte)
        print("  %2.0f-%2.0f %%      %5d %7.0f %% %9.0f %%"
              % (lo * 100, min(hi, 1) * 100, len(bøtte),
                 traff / len(bøtte) * 100, påstand * 100))

    sendt = [r for r in res if r[0] in ("opp", "ned") and r[1] >= terskel]
    if not sendt:
        print("\n  Ingen ville passert terskelen på %.0f %%." % (terskel * 100))
        return 0

    traff = sum(1 for d, _, f in sendt if rett(d, f))
    påstand = sum(c for _, c, _ in sendt) / len(sendt)
    se = math.sqrt(0.25 / len(sendt))
    z = (traff / float(len(sendt)) - 0.5) / se if se else 0

    print("\n  OVER TERSKELEN (%.0f %%): %d meldingar, %d rett = %.0f %%"
          % (terskel * 100, len(sendt), traff, traff / len(sendt) * 100))
    print("  Påstod %.0f %%. Skilnad %+.0f prosentpoeng."
          % (påstand * 100, (traff / float(len(sendt)) - påstand) * 100))
    print("  Mot myntkast: z=%+.1f -> %s"
          % (z, "betre enn tilfeldig" if z >= 2 else "IKKJE betre enn tilfeldig"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
