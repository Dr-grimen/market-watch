"""Får modellen rett når han seier at han er sikker?

Dette er det einaste som kan gjere eit confidence-tal verdt noko.

"80 % sikker" er i utgangspunktet berre ein påstand ein språkmodell
skriv om seg sjølv. Det er ikkje ein målt frekvens, og det finst ingen
grunn til å tru på det før nokon har sjekka. Ein modell kan godt seie
80 % og ha rett 55 % av gongane - det er den vanlegaste feilen som
finst hjå både menneske og maskinar, og han heiter overkonfidens.

Så: kvar einaste vurdering blir lagra saman med kva Nasdaq faktisk
gjorde etterpå. Etter nokre månader kan verktøyet svare på spørsmålet
med tal i staden for med ei kjensle:

    "Når eg har sagt 70-80 %, har eg hatt rett 61 % av gongane (n=34)."

Er det talet mykje lågare enn påstanden, er modellen overkonfident og
skal ikkje stolast på. Er det likt, er confidence-talet ekte. Begge
svara er nyttige. Å ikkje vite er det einaste som ikkje er det.

Merk at dette tek tid. Under ~30 vurderingar i ei bøtte er talet
meiningslaust, og det står det då også.
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "predictions.json"

# Bøtter å rapportere i. Grovare enn dette gøymer overkonfidens;
# finare enn dette gir for få i kvar bøtte til å seie noko.
BUCKETS = [(0.0, 0.4), (0.4, 0.6), (0.6, 0.75), (0.75, 0.9), (0.9, 1.01)]

MIN_FOR_VERDICT = 30

# Loggen blir klipt til dette. Sjå _tapt().
MAXROWS = 500


def _load():
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return []


def _save(rows):
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
    except OSError:
        pass


def record(local_date, direction, confidence, reference_price, kind="briefing"):
    """Lagrar ei vurdering som seinare skal dømmast.

    reference_price er Nasdaq-nivået i det vurderinga blei gjord. Utan
    det kan vi ikkje seie om han gjekk opp eller ned etterpå, og då er
    heile loggen verdilaus.
    """
    if reference_price is None:
        return False
    rows = _load()
    # Éi vurdering per dag per type. Køyrer verktøyet fleire gonger,
    # skal ikkje same dagen telje fem gonger og forureine statistikken.
    for row in rows:
        if row["date"] == local_date and row["kind"] == kind:
            return False
    rows.append({
        "date": local_date,
        "kind": kind,
        "direction": direction,
        "confidence": round(float(confidence), 3),
        "price": round(float(reference_price), 4),
        "logged_at": time.time(),
        "outcome": None,       # blir fylt inn seinare
        "actual_pct": None,
    })
    _save(rows[-MAXROWS:])
    return True


def settle(bars):
    """Dømmer gamle vurderingar mot kva som faktisk hende.

    bars er dagshistorikken for QQQ. For kvar ubedømd vurdering finn vi
    den fyrste ferdige dagen ETTER at ho blei gjord, og samanliknar.
    """
    rows = _load()
    if not rows or not bars:
        return 0

    # dato (YYYY-MM-DD) -> sluttkurs
    by_date = {}
    for bar in bars:
        parts = bar["date"].split("/")
        if len(parts) == 3:
            by_date["%s-%s-%s" % (parts[2], parts[0], parts[1])] = bar["close"]

    dates = sorted(by_date)
    settled = 0
    for row in rows:
        if row.get("outcome") is not None:
            continue
        later = [d for d in dates if d > row["date"]]
        if not later:
            continue
        close_after = by_date[later[0]]
        change = (close_after / row["price"] - 1.0) * 100.0
        row["actual_pct"] = round(change, 2)
        went_up = change > 0
        if row["direction"] == "opp":
            row["outcome"] = bool(went_up)
        elif row["direction"] == "ned":
            row["outcome"] = bool(not went_up)
        else:
            row["outcome"] = None      # "uklart" kan ikkje ha rett eller feil
            row["actual_pct"] = round(change, 2)
        settled += 1

    if settled:
        _save(rows)
    return settled


def _tapt(ever, n_rows):
    """Skil "tom fordi ny" frå "tom fordi noko forsvann".

    Dei to ser heilt like ut utanfrå, og det var nettopp difor ein
    mista logg kunne gøyme seg i månadsvis bak setninga "for få
    vurderingar enno". Teljaren ligg i state.json, loggen i
    predictions.json. Forsvinn den eine, avslører den andre det.

    MAXROWS er med fordi loggen med vilje blir klipt til dei siste 500.
    Utan den grensa ville verktøyet meldt tap kvar gong det passerte.
    """
    if not ever:
        return None
    forventa = min(ever, MAXROWS)
    if n_rows >= forventa:
        return None
    return forventa - n_rows


def report(ever=None):
    """Ei linje per bøtte: kva han påstod, mot kva han fekk til."""
    alle = _load()
    rows = [r for r in alle
            if r.get("outcome") is not None and r.get("direction") in ("opp", "ned")]

    tapt = _tapt(ever, len(alle))
    if tapt:
        åtvaring = ("ÅTVARING: %d vurderingar er gjorde, men berre %d ligg i "
                    "loggen. %d har gått tapt.\n  Fasiten byggjer seg ikkje "
                    "opp - sjekk at predictions.json overlever mellom øktene."
                    % (ever, len(alle), tapt))
    else:
        åtvaring = ""

    if not rows:
        grunn = ("Kalibrering: ingen vurderingar med retning er dømde enno. "
                 "Talet blir meiningsfullt etter nokre månader.")
        return (grunn + "\n  " + åtvaring) if åtvaring else grunn

    lines = ["Kalibrering - får han rett når han seier han er sikker?"]
    if åtvaring:
        lines.append("  " + åtvaring)
    for low, high in BUCKETS:
        subset = [r for r in rows if low <= r["confidence"] < high]
        if not subset:
            continue
        treff = sum(1 for r in subset if r["outcome"])
        n = len(subset)
        paastand = sum(r["confidence"] for r in subset) / n
        dom = "" if n >= MIN_FOR_VERDICT else "  (for få enno)"
        lines.append("  sa %2d-%2d %%: hadde rett %3.0f %% (n=%d, påstand %.0f %%)%s"
                     % (low * 100, min(high, 1.0) * 100,
                        treff / float(n) * 100, n, paastand * 100, dom))

    modne = [r for r in rows if r["confidence"] >= 0.6]
    if len(modne) >= MIN_FOR_VERDICT:
        treff = sum(1 for r in modne if r["outcome"]) / float(len(modne))
        paastand = sum(r["confidence"] for r in modne) / len(modne)
        if treff < paastand - 0.10:
            lines.append("  DOM: han er OVERKONFIDENT. Talet er høgare enn han fortener.")
        elif treff > paastand + 0.10:
            lines.append("  DOM: han er forsiktigare enn han treng vere.")
        else:
            lines.append("  DOM: confidence-talet stemmer nokolunde.")
    else:
        lines.append("  Ikkje nok vurderingar over 60 %% til å dømme han enno "
                     "(%d av %d)." % (len(modne), MIN_FOR_VERDICT))
    return "\n".join(lines)


def summary_line(ever=None):
    """Kort versjon, til meldingar."""
    alle = _load()
    rows = [r for r in alle
            if r.get("outcome") is not None and r.get("direction") in ("opp", "ned")]
    tapt = _tapt(ever, len(alle))
    if tapt:
        return ("Treffhistorikk: %d av %d vurderingar er borte frå loggen - "
                "fasiten tel ikkje." % (tapt, ever))
    if len(rows) < MIN_FOR_VERDICT:
        return "Treffhistorikk: %d vurderingar dømde - for få til å seie noko." % len(rows)
    treff = sum(1 for r in rows if r["outcome"])
    return "Treffhistorikk: %d av %d rett (%.0f %%)." % (
        treff, len(rows), treff / float(len(rows)) * 100)
