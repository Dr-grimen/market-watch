"""Køyrer modellen på historiske dagar og tel opp kor mange han fekk rett.

Dette er den eine testen som testar det Sondre faktisk får meldingar frå.
Backtesten testar dei mekaniske signala. Denne testar SPRÅKMODELLEN: seier
han 70 % og har rett 70 % av gongane, eller seier han 70 % og har rett 55 %?

Metoden:
  1. Vel tilfeldige dagar frå ein periode.
  2. For kvar dag: bygg opp nøyaktig det materialet verktøyet ville hatt,
     men KUTTA ved den dagen. Ingen data frå framtida kjem inn.
  3. Spør modellen: opp eller ned, og kor sikker?
  4. Sjekk fasit dagen etter.
  5. Grupper etter kva han sa, og samanlikn påstand mot treff.

Ei viktig avgrensing, som må stå tydeleg: vi har ikkje historiske
nyheiter. Modellen får chart, signal, basisrate og gap-statistikk, men
ikkje overskriftene frå den dagen. Han jobbar altså med mindre enn han
har til vanleg. Det gjer testen streng - og det gjer at eit godt
resultat her ville vore eit svært godt teikn.

Bruk:  .venv/bin/python kalibrer.py [tal_dagar]
"""

import json
import random
import sys
import time

import anthropic

from src.config import load_config, env
from src.sources import history
from src import analyze, ensemble, technicals as T

TEST_PROMPT = """Du er ein nøktern marknadsanalytikar.

Du får teknisk materiale om Nasdaq (QQQ) slik det såg ut ved slutten av \
ein handledag. Spørsmålet er enkelt: går kursen OPP eller NED neste \
handledag?

Du MÅ velje opp eller ned - "uklart" er ikkje eit gyldig svar her, fordi \
dette er ein test av kor godt du treffer. Men confidence skal vere ærleg: \
har du ikkje noko å gå på, sett han lågt (0.5 tyder myntkast).

VIKTIG: basisraten står i materialet. Aksjar stig oftare enn dei fell, så \
"opp" med 56 % er det same som å gjette blindt. Skal confidence over det, \
må du ha noko konkret.

Svar KUN med JSON: {"direction": "opp"|"ned", "confidence": 0.0-1.0, \
"reasoning": "maks 1 setning"}"""


def bygg_materiale(bars, cross, i):
    """Materialet slik det såg ut på dag i. Ingenting frå framtida.

    Vi skjer historikken ved i og reknar alt på nytt på den avkorta
    serien. Det er tregare enn å rekne éin gong og lese av indeks i,
    men det er umogleg å lekke framtid på denne måten - og det er
    viktigare enn farten når heile poenget er å ikkje lure seg sjølv.
    """
    kutt = bars[:i + 1]
    kryss = dict((k, v[:i + 1]) for k, v in cross.items())

    rapport = T.analyse(kutt, "QQQ (Nasdaq-100)")
    if not rapport:
        return None

    delar = [T.format_report(rapport), "", T.TECHNICAL_CAVEAT]

    res = ensemble.evaluate(kutt, kryss)
    if res:
        delar += ["", ensemble.format_report(res, kutt)]

    gap = T.gap_statistics(kutt)
    if gap and i > 0:
        rørsle = (kutt[-1]["close"] / kutt[-2]["close"] - 1) * 100
        tekst = T.gap_context(gap, rørsle, "Nasdaq")
        if tekst:
            delar += ["", "RØRSLE SISTE DAG:", tekst]

    return "<material>\n" + "\n".join(delar) + "\n</material>"


def spør(client, materiale):
    try:
        svar = client.messages.create(
            model=analyze.MODEL, max_tokens=300, system=TEST_PROMPT,
            messages=[{"role": "user", "content": materiale}],
        )
    except anthropic.RateLimitError:
        time.sleep(20)
        return None
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        print("  API-feil: %s" % exc)
        return None

    tekst = "".join(b.text for b in svar.content if getattr(b, "type", "") == "text")
    data = analyze._extract_json(tekst)
    if not isinstance(data, dict):
        return None
    retning = data.get("direction")
    if retning not in ("opp", "ned"):
        return None
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        return None
    return {"direction": retning, "confidence": conf,
            "reasoning": str(data.get("reasoning", ""))[:160]}


def main():
    antal = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    load_config()
    nøkkel = env("ANTHROPIC_API_KEY")
    if not nøkkel:
        print("ANTHROPIC_API_KEY manglar.")
        return 1

    bars = history.fetch_daily("QQQ")
    cross = dict((k, ensemble._aligned(bars, v))
                 for k, v in ensemble.load_cross().items())
    closes = [b["close"] for b in bars]

    # Berre dagar godt etter oppvarminga, og ikkje den aller siste.
    lovlege = list(range(T.WARMUP + 250, len(bars) - 1))
    random.seed(42)                       # same utval kvar gong = samanliknbart
    dagar = sorted(random.sample(lovlege, min(antal, len(lovlege))))

    print("Kalibrering: %d tilfeldige dagar mellom %s og %s\n"
          % (len(dagar), bars[dagar[0]]["date"], bars[dagar[-1]]["date"]))

    client = anthropic.Anthropic(api_key=nøkkel)
    resultat = []
    for teller, i in enumerate(dagar, 1):
        materiale = bygg_materiale(bars, cross, i)
        if not materiale:
            continue
        svar = spør(client, materiale)
        if not svar:
            continue

        gjekk_opp = closes[i + 1] > closes[i]
        rett = (svar["direction"] == "opp") == gjekk_opp
        endring = (closes[i + 1] / closes[i] - 1) * 100
        resultat.append({
            "dato": bars[i]["date"], "sa": svar["direction"],
            "conf": svar["confidence"], "rett": rett, "endring": endring,
        })
        print("  %3d/%d  %s  sa %-3s %3.0f %%  ->  %+5.2f %%  %s"
              % (teller, len(dagar), bars[i]["date"], svar["direction"],
                 svar["confidence"] * 100, endring, "RETT" if rett else "feil"))

    if not resultat:
        print("\nIngen svar kom gjennom.")
        return 1

    with open("kalibrering.json", "w", encoding="utf-8") as fh:
        json.dump(resultat, fh)

    # ---- Domen ----
    n = len(resultat)
    rett = sum(1 for r in resultat if r["rett"])
    opp_dagar = sum(1 for r in resultat if r["endring"] > 0)
    basis = opp_dagar / float(n)

    print("\n" + "=" * 66)
    print("DOM  (n=%d)" % n)
    print("=" * 66)
    print("  Modellen traff        : %d av %d  = %.1f %%" % (rett, n, rett / float(n) * 100))
    print("  Sa 'opp'              : %d gonger" % sum(1 for r in resultat if r["sa"] == "opp"))
    print("  Gjekk faktisk opp     : %d av %d  = %.1f %%" % (opp_dagar, n, basis * 100))
    print("  Alltid 'opp' ville gitt: %.1f %%" % (basis * 100))
    kant = rett / float(n) - basis
    print("  KANT over å berre seie 'opp': %+.1f prosentpoeng" % (kant * 100))

    print("\n  Kalibrering - stemmer talet han oppgir?")
    for lo, hi in ((0.0, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 1.01)):
        bøtte = [r for r in resultat if lo <= r["conf"] < hi]
        if not bøtte:
            continue
        traff = sum(1 for r in bøtte if r["rett"]) / float(len(bøtte))
        påstand = sum(r["conf"] for r in bøtte) / len(bøtte)
        merk = "" if len(bøtte) >= 15 else "  (for få)"
        print("    sa %2d-%2d %%: hadde rett %3.0f %%  (n=%2d, påstand %.0f %%)%s"
              % (lo * 100, min(hi, 1.0) * 100, traff * 100, len(bøtte),
                 påstand * 100, merk))

    høge = [r for r in resultat if r["conf"] >= 0.65]
    if høge:
        traff = sum(1 for r in høge if r["rett"]) / float(len(høge))
        påstand = sum(r["conf"] for r in høge) / len(høge)
        print("\n  DEI SOM VILLE GITT DEG MELDING (65 %% eller over):")
        print("    %d stk, påstod %.0f %%, hadde rett %.0f %%"
              % (len(høge), påstand * 100, traff * 100))
        if traff < påstand - 0.10:
            print("    -> OVERKONFIDENT. Talet er høgare enn han fortener.")
        elif traff < basis:
            print("    -> Dårlegare enn å berre seie 'opp' kvar dag.")
        else:
            print("    -> Held det han lovar.")
    else:
        print("\n  Ingen av dagane nådde 65 %%. Du ville fått null meldingar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
