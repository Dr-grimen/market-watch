"""Mange små målte kantar i staden for éin sjølvsikker spådom.

Medallion-fondet har ein treffprosent på 50,75 og har tent over hundre
milliardar dollar. Dei vinn ikkje fordi dei er sikre - dei er så vidt
betre enn eit myntkast. Dei vinn fordi dei har 300 000 uavhengige,
bittesmå kantar per dag, og fordi ingen av dei kan skade dei åleine.

Vi kan ikkje gjere 300 000 handlar. Men vi kan gjere det same med
VURDERINGA: i staden for å be éin språkmodell om eitt sjølvsikkert tal,
reknar vi ut fleire uavhengige signal, måler kva kvart av dei har vore
verdt historisk, og ser om dei peikar same veg.

To reglar som er heile poenget:

  1. Ingen vekter er gjetta. Kvart signal blir backtesta på QQQ si eiga
     historie, og vekta er den MÅLTE kanten over basisraten. Eit signal
     som ikkje slår basisraten får vekt null, uansett kor fornuftig det
     høyrest ut.

  2. Er signala usamde, er svaret usikkert. Det er ikkje ein feil i
     modellen - det er det sanne svaret, og det er det vanlegaste.

Signala er med vilje henta frå ulike stader: trend, momentum,
motrørsle, halvleiarar, renter og risikovilje. Seks signal som alle
kjem frå same kurve er berre eitt signal med seks namn.
"""

import math

from . import technicals as T
from .sources import history

# Kvar av desse er eit eige instrument, så signala ikkje berre er
# QQQ-kurva sagd på seks ulike måtar.
CROSS_ASSETS = {
    "smh": "SMH",     # halvleiarar - leier Nasdaq
    "tlt": "TLT",     # lange statsobligasjonar - opp = fallande rente
    "vixy": "VIXY",   # volatilitet - opp = frykt
}

MIN_SAMPLE = 60          # under dette måler vi ikkje, vi gjettar

# Same strenge krav som lysestake-mønstera blir haldne til. Vi testar 7
# signal i to retningar - 14 testar - så ved z=1,5 er det venta at
# rundt to av dei ser gode ut på rein flaks. Å godta ein låg terskel her
# medan candle-mønstera må ha z=3 ville vore dobbeltmoral, og verre:
# det ville sleppt inn nettopp den typen tilfeldig funn som får eit
# verktøy til å verke treffsikkert utan å vere det.
NOISE_Z = 2.5


def _aligned(base_bars, other_bars):
    """Same dagar i begge seriane, elles samanliknar vi epler og pærer."""
    other = {}
    for bar in other_bars:
        other[bar["date"]] = bar
    out = []
    for i, bar in enumerate(base_bars):
        match = other.get(bar["date"])
        out.append(match)
    return out


def _pct_change(bars, i):
    if i <= 0 or bars[i] is None or bars[i - 1] is None:
        return None
    prev = bars[i - 1]["close"]
    if not prev:
        return None
    return (bars[i]["close"] / prev - 1.0) * 100.0


def build_signals(bars, cross):
    """Alle signala som funksjonar av indeks i. Ingen ser inn i framtida."""
    ctx = T.Context(bars)
    smh = cross.get("smh") or []
    tlt = cross.get("tlt") or []
    vixy = cross.get("vixy") or []

    def trend(i):
        if None in (ctx.sma50[i], ctx.sma200[i]):
            return None
        close = bars[i]["close"]
        if close > ctx.sma50[i] > ctx.sma200[i]:
            return "opp"
        if close < ctx.sma50[i] < ctx.sma200[i]:
            return "ned"
        return None

    def momentum(i):
        h = ctx.macd_h[i]
        if h is None:
            return None
        return "opp" if h > 0 else "ned"

    def motroersle(i):
        r = ctx.rsi14[i]
        if r is None:
            return None
        if r < 35:
            return "opp"
        if r > 70:
            return "ned"
        return None

    def to_ned_dagar(i):
        if i < 2:
            return None
        if bars[i]["close"] < bars[i - 1]["close"] < bars[i - 2]["close"]:
            return "opp"      # motrørsle etter to fall
        return None

    def halvleiarar(i):
        """Leier SOX, eller heng han etter?"""
        a, b = _pct_change(smh, i), _pct_change(bars, i)
        if a is None or b is None:
            return None
        skilnad = a - b
        if abs(skilnad) < 0.5:
            return None
        return "opp" if skilnad > 0 else "ned"

    def renter(i):
        """TLT opp = fallande rente = godt for vekstaksjar."""
        a = _pct_change(tlt, i)
        if a is None or abs(a) < 0.4:
            return None
        return "opp" if a > 0 else "ned"

    def risikovilje(i):
        """VIXY ned = mindre frykt."""
        a = _pct_change(vixy, i)
        if a is None or abs(a) < 3.0:
            return None
        return "ned" if a > 0 else "opp"

    return [
        ("Trend (SMA50/200)", trend),
        ("Momentum (MACD)", momentum),
        ("Motrørsle (RSI)", motroersle),
        ("To fall på rad", to_ned_dagar),
        ("Halvleiarar (SMH)", halvleiarar),
        ("Renter (TLT)", renter),
        ("Risikovilje (VIXY)", risikovilje),
    ]


def _stable(closes, fn, retning, start, stop, forventa):
    """Held kanten seg i begge halvdelane av historikken?"""
    midt = (start + stop) // 2
    for lo, hi in ((start, midt), (midt, stop)):
        treff = n = 0
        for i in range(lo, hi):
            try:
                if fn(i) != retning:
                    continue
            except (TypeError, IndexError):
                continue
            n += 1
            if (retning == "opp") == (closes[i + 1] > closes[i]):
                treff += 1
        if n < 20:
            return False
        if treff / float(n) - forventa <= 0:
            return False
    return True


def measure(bars, signals):
    """Kva har kvart signal VORE verdt? Ingen vekter er gjetta.

    For kvart signal: dei dagane det sa 'opp', kor ofte gjekk det opp
    dagen etter - mot basisraten? Kanten er skilnaden, og z fortel om
    han er noko anna enn flaks.
    """
    closes = [b["close"] for b in bars]
    start, stop = T.WARMUP, len(closes) - 1
    ups = sum(1 for i in range(start, stop) if closes[i + 1] > closes[i])
    total = stop - start
    base = ups / float(total) if total else 0.5

    målt = {}
    for name, fn in signals:
        for retning in ("opp", "ned"):
            treff = n = 0
            for i in range(start, stop):
                try:
                    if fn(i) != retning:
                        continue
                except (TypeError, IndexError):
                    continue
                n += 1
                gjekk_opp = closes[i + 1] > closes[i]
                if (retning == "opp") == gjekk_opp:
                    treff += 1
            if n < MIN_SAMPLE:
                målt[(name, retning)] = {"n": n, "usable": False}
                continue
            rate = treff / float(n)
            # Riktig samanlikning: sa signalet 'ned', er fasiten
            # kor ofte det GJEKK ned, altså 1 - basisrate.
            forventa = base if retning == "opp" else 1.0 - base
            kant = rate - forventa
            se = math.sqrt(forventa * (1 - forventa) / n)
            z = kant / se if se > 0 else 0.0
            # Og sjølv z over terskelen held ikkje aleine: kanten må
            # peike same veg i BEGGE halvdelane av historikken. Eit
            # signal som berre verka i 2020 er ikkje eit signal, det er
            # eit minne om ein marknad som ikkje finst lenger.
            stabil = _stable(closes, fn, retning, start, stop, forventa)
            tel = abs(z) >= NOISE_Z and stabil
            målt[(name, retning)] = {
                "n": n, "usable": True, "rate": rate, "base": forventa,
                "edge": kant, "z": z, "stable": stabil,
                # Vekt null når kanten ikkje skil seg frå støy. Eit signal
                # som høyrest fornuftig ut, men ikkje måler noko, skal
                # ikkje få lov til å dra vurderinga.
                "weight": kant if tel else 0.0,
            }
    return base, målt


def evaluate(bars, cross):
    """Kva seier signala i dag, og kor mykje er dei verdt?"""
    if not bars or len(bars) < T.WARMUP + 100:
        return None

    signals = build_signals(bars, cross)
    base, målt = measure(bars, signals)
    last = len(bars) - 1

    stemmer = []
    for name, fn in signals:
        try:
            sier = fn(last)
        except (TypeError, IndexError):
            sier = None
        if sier is None:
            continue
        stat = målt.get((name, sier), {})
        stemmer.append({
            "name": name, "says": sier,
            "n": stat.get("n", 0),
            "rate": stat.get("rate"),
            "edge": stat.get("edge", 0.0),
            "z": stat.get("z", 0.0),
            "weight": stat.get("weight", 0.0),
            "usable": stat.get("usable", False),
        })

    med_vekt = [s for s in stemmer if s["weight"] != 0.0]
    netto = 0.0
    for s in med_vekt:
        netto += s["weight"] if s["says"] == "opp" else -s["weight"]

    if not med_vekt:
        retning, semje = "uklart", 0.0
    else:
        opp = sum(1 for s in med_vekt if s["says"] == "opp")
        semje = max(opp, len(med_vekt) - opp) / float(len(med_vekt))
        if abs(netto) < 0.01:
            retning = "uklart"
        else:
            retning = "opp" if netto > 0 else "ned"

    return {
        "base_rate": base,
        "votes": stemmer,
        "weighted": med_vekt,
        "net": netto,
        "agreement": semje,
        "direction": retning,
    }


def load_cross():
    """Hentar dei andre instrumenta. Cache gjer dette gratis etter fyrste gong."""
    out = {}
    for key, symbol in CROSS_ASSETS.items():
        out[key] = history.fetch_daily(symbol, "etf")
    return out


def format_report(result, bars):
    """Til modellen: kva kvart signal seier, og kva det har vore verdt."""
    if not result:
        return ""

    lines = ["SIGNALSAMLING (kvar vekt er MÅLT på QQQ si eiga historie,",
             "ikkje gjetta. Signal utan målt kant har vekt null.):",
             "  Basisrate: %.0f %% av alle dagar går opp." % (result["base_rate"] * 100)]

    if not result["votes"]:
        lines.append("  Ingen av signala slår ut i dag.")
        return "\n".join(lines)

    # Juster indeksane slik at cross-lista er på linje med bars.
    for vote in result["votes"]:
        if not vote["usable"]:
            lines.append("  %-20s seier %-5s | berre n=%d - for lite, vekt 0"
                         % (vote["name"], vote["says"], vote["n"]))
            continue
        merke = "TEL" if vote["weight"] else "vekt 0 (støy)"
        lines.append("  %-20s seier %-5s | traff %.0f %% (n=%d), kant %+.1f pp, z=%+.1f | %s"
                     % (vote["name"], vote["says"], vote["rate"] * 100, vote["n"],
                        vote["edge"] * 100, vote["z"], merke))

    if result["weighted"]:
        lines.append("  SUM: %d signal med målt kant, %.0f %% av dei er samde. "
                     "Netto peikar %s."
                     % (len(result["weighted"]), result["agreement"] * 100,
                        result["direction"]))
    else:
        lines.append("  SUM: ingen av signala som slo ut har målt kant. "
                     "Dei seier ingenting.")
    lines.append("  Er signala usamde, er usikkert det RIKTIGE svaret - "
                 "ikkje eit teikn på at du skal leite vidare.")
    return "\n".join(lines)
