"""Korleis dagen faktisk utviklar seg, minutt for minutt.

Fram til no las verktøyet to ting: kva som blir SKRIVE om marknaden, og
kva dagsbarane har gjort HISTORISK. Det som mangla var å lese marknaden
medan han går.

Skilnaden er ikkje akademisk. Desse to dagane har same sluttkurs:

    A: opnar +0,2 %, klatrar jamt heile dagen, endar +0,9 % på toppen
    B: opnar +1,4 %, fell tilbake heile dagen, endar +0,9 % på botnen

Same tal i avisa. Heilt ulik dag. Den fyrste viser kjøparar som held;
den andre viser at seljarane tok over. Ei melding som ikkje ser
skilnaden les ikkje marknaden - ho les eit referat av han.

Kjelda er api.nasdaq.com sitt chart-endepunkt: 375 minuttpunkt frå
førhandel kl. 04:00 ET og fram til no. Gratis, utan nøkkel, same som
resten.
"""

import requests

URL = "https://api.nasdaq.com/api/quote/%s/chart"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _minutt(punkt):
    """'10:14 AM ET' -> minutt sidan midnatt. None når det ikkje går."""
    tekst = ((punkt.get("z") or {}).get("dateTime") or "").replace(" ET", "").strip()
    if not tekst:
        return None
    try:
        klokke, ampm = tekst.rsplit(" ", 1)
        time_, minutt = [int(x) for x in klokke.split(":")]
    except ValueError:
        return None
    if ampm.upper() == "PM" and time_ != 12:
        time_ += 12
    elif ampm.upper() == "AM" and time_ == 12:
        time_ = 0
    return time_ * 60 + minutt


def fetch(symbol="QQQ", assetclass="etf", timeout=20):
    """Returnerer [(minutt_ET, kurs), ...] frå i dag. Tom liste ved feil."""
    try:
        resp = requests.get(URL % symbol, params={"assetclass": assetclass},
                            headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        rader = ((resp.json().get("data") or {}).get("chart")) or []
    except (requests.RequestException, ValueError):
        return []

    ut = []
    for punkt in rader:
        try:
            kurs = float(punkt.get("y"))
        except (TypeError, ValueError):
            continue
        minutt = _minutt(punkt)
        if minutt is None or kurs <= 0:
            continue
        ut.append((minutt, kurs))
    ut.sort()
    return ut


# Amerikansk børs opnar 09:30 ET og stengjer 16:00.
OPNING = 9 * 60 + 30
STENGING = 16 * 60


def analyse(punkt, forrige_slutt=None):
    """Kva har dagen gjort, og kva gjer han akkurat no?"""
    if len(punkt) < 20:
        return None

    ordinaer = [(m, k) for m, k in punkt if OPNING <= m <= STENGING]
    forhandel = [(m, k) for m, k in punkt if m < OPNING]

    # Er børsen ikkje opna enno, er førhandelen alt vi har.
    aktiv = ordinaer if len(ordinaer) >= 10 else punkt
    if len(aktiv) < 10:
        return None

    kursar = [k for _, k in aktiv]
    aapning, no_ = kursar[0], kursar[-1]
    topp, botn = max(kursar), min(kursar)

    # Kvar i dagens spenn ligg vi? 1.0 = på toppen, 0.0 = på botnen.
    spenn = topp - botn
    plassering = (no_ - botn) / spenn if spenn > 0 else 0.5

    # Siste timen mot resten av dagen: held rørsla, eller ebbar ho ut?
    siste_min = aktiv[-1][0]
    siste_time = [k for m, k in aktiv if m >= siste_min - 60]
    trend_siste = ((siste_time[-1] / siste_time[0] - 1) * 100
                   if len(siste_time) > 2 and siste_time[0] else 0.0)

    return {
        "aapning": aapning,
        "no": no_,
        "topp": topp,
        "botn": botn,
        "fra_aapning": (no_ / aapning - 1) * 100 if aapning else 0.0,
        "fra_forrige": ((no_ / forrige_slutt - 1) * 100
                        if forrige_slutt else None),
        "spenn_pct": (spenn / aapning * 100) if aapning else 0.0,
        "plassering": plassering,
        "siste_time": trend_siste,
        "forhandel": len(forhandel) > 5,
        "opna": len(ordinaer) >= 10,
        "punkt": len(aktiv),
    }


def format_report(a, label="Nasdaq", snitt_spenn=None):
    """Ei skildring av dagen, ikkje ei liste med tal."""
    if not a:
        return ""

    if not a["opna"]:
        lead = "%s har ikkje opna enno. I førhandelen:" % label
    else:
        lead = "%s i dag, medan han går:" % label

    lines = [lead]
    lines.append("  Opna %.2f, er %.2f no (%+.2f %% frå opning)."
                 % (a["aapning"], a["no"], a["fra_aapning"]))
    lines.append("  Dagens spenn: %.2f til %.2f (%.2f %% breitt)."
                 % (a["botn"], a["topp"], a["spenn_pct"]))

    # Kvar i spennet - det seier mest om kven som har kontrollen.
    p = a["plassering"]
    if p >= 0.8:
        kvar = "heilt oppe ved dagens topp - kjøparane held"
    elif p <= 0.2:
        kvar = "heilt nede ved dagens botn - seljarane held"
    elif p >= 0.6:
        kvar = "i øvre del av spennet"
    elif p <= 0.4:
        kvar = "i nedre del av spennet"
    else:
        kvar = "midt i spennet - ingen har overtaket"
    lines.append("  Ligg %s (%.0f %% opp i spennet)." % (kvar, p * 100))

    # Siste timen: held rørsla eller snur ho?
    if abs(a["siste_time"]) >= 0.15:
        retning = "opp" if a["siste_time"] > 0 else "ned"
        samstemt = (a["siste_time"] > 0) == (a["fra_aapning"] > 0)
        merknad = ("same veg som resten av dagen" if samstemt
                   else "MOTSETT av resten av dagen - rørsla snur")
        lines.append("  Siste timen: %+.2f %% (%s, %s)."
                     % (a["siste_time"], retning, merknad))
    else:
        lines.append("  Siste timen: flat - rørsla har stoppa opp.")

    # Er dagen stor eller vanleg? Utan dette veit ingen om 0,8 % er mykje.
    if snitt_spenn:
        forhold = a["spenn_pct"] / snitt_spenn
        if forhold >= 1.5:
            lines.append("  Spennet er %.1fx ein vanleg dag - dette er ein "
                         "STOR dag." % forhold)
        elif forhold <= 0.6:
            lines.append("  Spennet er berre %.1fx ein vanleg dag - roleg."
                         % forhold)
        else:
            lines.append("  Spennet er normalt for dette instrumentet.")

    return "\n".join(lines)


def snitt_dagsspenn(bars, dagar=60):
    """Kor breitt plar ein dag vere? Utan dette er dagens spenn eit tal utan meining."""
    siste = [b for b in bars[-dagar:] if b.get("open")]
    if not siste:
        return None
    spenn = [(b["high"] - b["low"]) / b["open"] * 100 for b in siste if b["open"]]
    return sum(spenn) / len(spenn) if spenn else None
