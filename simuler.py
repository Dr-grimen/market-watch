"""Kva ville du fått dei siste tre månadene, og hadde det stemt?

Sondre sitt spørsmål: "koffor må eg tape penger først". Han har rett.
Historia ligg der, og ein simulering kostar kroner i staden for pengar.

Skilnaden frå kalibrer_hendingar.py er viktig: den testar berre dagar
der eit stort tal bomma - altså dei mest lovande dagane. Denne går
gjennom KVAR EINASTE handledag, akkurat slik verktøyet gjer i drift.
Det gir det ærlege svaret på to spørsmål:

  1. Kor mange meldingar ville han fått?
  2. Kor mange av dei var rette?

Det andre er sjølvsagt det viktigaste. Men det fyrste er ikkje langt bak:
eit verktøy som seier noko kvar dag er noko heilt anna enn eitt som seier
noko to gonger i månaden, og begge kan ha same treffprosent.

Nyheitene kjem frå GDELT sitt opne arkiv, henta i vindauget 04-13 UTC
den aktuelle dagen - altså natta og morgonen fram til rett før den
amerikanske opninga. Modellen ser aldri reaksjonen han skal spå.

Avgrensinga som står att: GDELT si kjeldeliste og rangering er ikkje
identisk med dei 103 feedane i drift. Simuleringa er ei god tilnærming,
ikkje ein perfekt rekonstruksjon.

Bruk:  .venv/bin/python simuler.py [tal_dagar]
"""

import concurrent.futures
import math
import sys

from src.config import load_config, env
from src.sources import history, calendar as cal, arkiv
from src import analyze, ensemble, technicals as T


def bygg(bars, kryss_full, closes, i, dato_iso, nøkkel):
    """Materialet slik det såg ut den morgonen. Ingen lookahead."""
    kutt = bars[:i + 1]
    kryss = dict((k, v[:i + 1]) for k, v in kryss_full.items())

    rapport = T.analyse(kutt, "QQQ (Nasdaq-100)")
    teknisk = T.format_report(rapport) if rapport else ""

    gap = T.gap_statistics(kutt)
    if gap and i > 0:
        tekst = T.gap_context(gap, (closes[i] / closes[i - 1] - 1) * 100, "Nasdaq")
        if tekst:
            teknisk += "\n\nRØRSLE SISTE DAG:\n" + tekst

    res = ensemble.evaluate(kutt, kryss)
    sig = ensemble.format_report(res, kutt) if res else ""

    verd = []
    for namn, nykel in (("Halvleiarar (SMH)", "smh"),
                        ("Lange renter (TLT)", "tlt"),
                        ("Volatilitet (VIXY)", "vixy")):
        serie = kryss_full.get(nykel) or []
        if i < len(serie) and serie[i] and serie[i - 1]:
            verd.append("  %s: %+.2f %%"
                        % (namn, (serie[i]["close"] / serie[i - 1]["close"] - 1) * 100))

    # Historiske overskrifter frå GDELT, henta i vindauget 04-13 UTC -
    # altså natta og morgonen, før den amerikanske opninga. Utan desse
    # seier modellen "uklart" kvar einaste dag, og simuleringa måler
    # ingenting.
    nyheiter = arkiv.hent(dato_iso)

    return analyze.evaluate(
        nyheiter,
        "Nasdaq (QQQ) siste slutt %.2f (%+.2f %% frå dagen før)"
        % (closes[i], (closes[i] / closes[i - 1] - 1) * 100),
        context_note="Dette er morgonvurderinga før børsen opnar.",
        api_key=nøkkel,
        calendar_summary=cal.format_calendar(cal.fetch_today(dato_iso)),
        technical_summary=teknisk,
        ensemble_summary=sig,
        world_summary="\n".join(verd),
        system_prompt=analyze.BRIEFING_PROMPT,
    )


def main():
    dagar = int(sys.argv[1]) if len(sys.argv) > 1 else 65
    cfg = load_config()
    nøkkel = env("ANTHROPIC_API_KEY")
    if not nøkkel:
        print("ANTHROPIC_API_KEY manglar.")
        return 1
    terskel = cfg["confidence_threshold"]

    bars = history.fetch_daily("QQQ")
    closes = [b["close"] for b in bars]
    kryss_full = dict((k, ensemble._aligned(bars, v))
                      for k, v in ensemble.load_cross().items())

    start = max(T.WARMUP + 1, len(bars) - 1 - dagar)
    indeksar = list(range(start, len(bars) - 1))
    print("Simulerer %d handledagar: %s til %s\n"
          % (len(indeksar), bars[start]["date"], bars[-2]["date"]))

    def ein(i):
        p = bars[i]["date"].split("/")
        dato = "%s-%s-%s" % (p[2], p[0], p[1])
        try:
            v = bygg(bars, kryss_full, closes, i, dato, nøkkel)
            if not v:
                return None
            return (bars[i]["date"], v["direction"], v["confidence"],
                    (closes[i + 1] / closes[i] - 1) * 100)
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        res = [r for r in pool.map(ein, indeksar) if r]

    if not res:
        print("Ingen svar kom gjennom.")
        return 1

    # Lagra raadataa. Da kan ein sjaa kva ULIKE terskelar ville gitt utan
    # aa betale for 65 nye kall - og det er nettopp det spoersmaalet som
    # avgjer om verktoeyet er brukbart.
    import json
    with open("simulering.json", "w", encoding="utf-8") as fh:
        json.dump([{"dato": d, "retning": r, "conf": c, "faktisk": f}
                   for d, r, c, f in res], fh)
    print("(raadata lagra i simulering.json)\n")

    def rett(d, endring):
        return (d == "opp" and endring > 0) or (d == "ned" and endring < 0)

    sendt = [r for r in res if r[1] in ("opp", "ned") and r[2] >= terskel]
    grå = len(res) - len(sendt)

    print("KVA DU VILLE FÅTT (terskel %.0f %%):\n" % (terskel * 100))
    print("  Grå dag            : %3d av %d  (%.0f %%)"
          % (grå, len(res), grå / float(len(res)) * 100))
    print("  Melding med retning: %3d av %d  (%.0f %%)"
          % (len(sendt), len(res), len(sendt) / float(len(res)) * 100))
    if len(res) >= 20:
        print("  -> ca. %.1f meldingar i månaden" % (len(sendt) / (len(res) / 21.0)))

    if not sendt:
        print("\n  Ingen meldingar i det heile. Ingenting å måle.")
        return 0

    print("\n  DEI SOM VILLE GÅTT UT:\n")
    print("    %-12s %-5s %5s %9s  %s" % ("dato", "sa", "conf", "faktisk", "dom"))
    print("    " + "-" * 46)
    for dato, d, c, f in sendt:
        print("    %-12s %-5s %4.0f%% %+8.2f %%  %s"
              % (dato, d.upper(), c * 100, f, "rett" if rett(d, f) else "feil"))

    traff = sum(1 for _, d, _, f in sendt if rett(d, f))
    påstand = sum(c for _, _, c, _ in sendt) / len(sendt)
    andel = traff / float(len(sendt))

    # Basisrate: kor ofte gjekk det opp i same perioden?
    opp = sum(1 for _, _, _, f in res if f > 0) / float(len(res))

    se = math.sqrt(0.25 / len(sendt))
    z = (andel - 0.5) / se if se else 0

    print("\n  RESULTAT: %d av %d rett = %.0f %%" % (traff, len(sendt), andel * 100))
    print("  Han påstod %.0f %%. Skilnad %+.0f prosentpoeng."
          % (påstand * 100, (andel - påstand) * 100))
    print("  Basisrate i perioden: %.0f %% opp-dagar." % (opp * 100))
    print("  Mot myntkast: z=%+.1f -> %s"
          % (z, "betre enn tilfeldig" if z >= 2 else "IKKJE skiljeleg frå tilfeldig"))

    # Kva ville skjedd med pengane? Enkel rekning, ei eining per melding.
    sum_avk = sum(f if d == "opp" else -f for _, d, _, f in sendt)
    print("\n  Om du hadde handla kvar melding (utan giring, utan kostnad):")
    print("    samla %+.2f %% over %d handlar, snitt %+.2f %% per handel"
          % (sum_avk, len(sendt), sum_avk / len(sendt)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
