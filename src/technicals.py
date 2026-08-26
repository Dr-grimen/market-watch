"""Chartlesing med tal bak.

Dette laget les det same som ein tradar les i eit chart - trend, RSI,
MACD, Bollinger, lysestake-mønster - men det stoggar ikkje der. For kvart
mønster som slår ut i dag reknar det ut kva som FAKTISK hende dei
førre gongane same mønster slo ut i akkurat dette instrumentet.

Grunnen er enkel: "det danna seg ein hammar" er ikkje informasjon. "Det
danna seg ein hammar, det har skjedd 71 gonger før, og 58 % av dei
gongane steig kursen dagen etter - mot 54 % på ein tilfeldig dag" ER
informasjon. Og med n=71 er skilnaden på 4 prosentpoeng godt innanfor
det flaks kan forklare, noko modellen får beskjed om.

Difor blir tre tal alltid rapporterte saman:
  - treffprosent      kor ofte det gjekk rett veg
  - basisrate         kor ofte det går den vegen på ein KVA SOM HELST dag
  - z                 kor mange standardfeil kanten er unna null

Ein kant utan z er ei løgn. Nesten alle lysestake-mønster har z under 2,
og det skal dei få lov til å vise. Det er slik dette verktøyet unngår å
bli ein spelautomat som finn eit mønster kvar einaste dag.
"""

import math

# Utan dette mange barane er indikatorane ikkje varme enno.
WARMUP = 210

MIN_SAMPLE = 20      # Færre tilfelle enn dette er anekdotar, ikkje statistikk.
SIGNIFICANT_Z = 2.0  # Under dette kallar vi det støy, uansett kor pent det ser ut.

# Og over 2 held heller ikkje åleine. Vi testar 29 mønster på to
# horisontar for tre instrument - 174 testar. Ved z=2 er det venta at
# rundt 9 av dei slår ut på rein flaks. Difor finst det eit strengare
# nivå, og berre det får lov til å påverke ei avgjerd.
STRONG_Z = 3.0
TESTS_RUN = 174


# ---------------------------------------------------------------- indikatorar

def sma(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    total = sum(values[:n])
    out[n - 1] = total / n
    for i in range(n, len(values)):
        total += values[i] - values[i - n]
        out[i] = total / n
    return out


def ema(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes, n=14):
    """Wilder si utgåve - den same som ligg i handelsplattformene."""
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        delta = closes[i] - closes[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain, avg_loss = gains / n, losses / n
    out[n] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1 + avg_gain / avg_loss)
    for i in range(n + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(delta, 0.0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-delta, 0.0)) / n
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1 + avg_gain / avg_loss)
    return out


def macd_hist(closes, fast=12, slow=26, signal=9):
    fast_line, slow_line = ema(closes, fast), ema(closes, slow)
    line = [None] * len(closes)
    for i in range(len(closes)):
        if fast_line[i] is not None and slow_line[i] is not None:
            line[i] = fast_line[i] - slow_line[i]

    defined = [v for v in line if v is not None]
    sig_tail = ema(defined, signal)
    offset = len(line) - len(defined)

    hist = [None] * len(closes)
    for j, value in enumerate(sig_tail):
        if value is not None and line[offset + j] is not None:
            hist[offset + j] = line[offset + j] - value
    return line, hist


def atr(bars, n=14):
    """Gjennomsnittleg sant utslag - kor mykje instrumentet plar røre seg."""
    out = [None] * len(bars)
    if len(bars) < n + 1:
        return out
    trs = [None]
    for i in range(1, len(bars)):
        prev_close = bars[i - 1]["close"]
        trs.append(max(
            bars[i]["high"] - bars[i]["low"],
            abs(bars[i]["high"] - prev_close),
            abs(bars[i]["low"] - prev_close),
        ))
    prev = sum(trs[1:n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(bars)):
        prev = (prev * (n - 1) + trs[i]) / n
        out[i] = prev
    return out


def bollinger(closes, n=20, mult=2.0):
    mid = sma(closes, n)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    width = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        window = closes[i - n + 1:i + 1]
        mean = mid[i]
        var = sum((c - mean) ** 2 for c in window) / n
        sd = math.sqrt(var)
        upper[i] = mean + mult * sd
        lower[i] = mean - mult * sd
        width[i] = (upper[i] - lower[i]) / mean if mean else None
    return upper, mid, lower, width


# ------------------------------------------------------------------- kontekst

class Context(object):
    """Alt som må reknast ut éin gong og brukast mange gonger."""

    def __init__(self, bars):
        self.bars = bars
        closes = [b["close"] for b in bars]
        volumes = [b["volume"] for b in bars]
        self.closes = closes
        self.sma20 = sma(closes, 20)
        self.sma50 = sma(closes, 50)
        self.sma200 = sma(closes, 200)
        self.rsi14 = rsi(closes, 14)
        self.macd_line, self.macd_h = macd_hist(closes)
        self.atr14 = atr(bars, 14)
        self.bb_up, self.bb_mid, self.bb_low, self.bb_width = bollinger(closes)
        self.vol20 = sma(volumes, 20)


def _body(bar):
    return bar["close"] - bar["open"]


def _range(bar):
    return bar["high"] - bar["low"]


def _upper_shadow(bar):
    return bar["high"] - max(bar["open"], bar["close"])


def _lower_shadow(bar):
    return min(bar["open"], bar["close"]) - bar["low"]


# -------------------------------------------------------------------- mønster
# Kvar detektor svarer på: slo dette mønsteret ut på bar nummer i?
# Dei må vere reine funksjonar av fortida, elles blir statistikken juks.

def p_doji(b, c, i):
    rng = _range(b[i])
    return rng > 0 and abs(_body(b[i])) <= 0.1 * rng


def p_hammer(b, c, i):
    bar, rng = b[i], _range(b[i])
    if rng <= 0 or c.sma20[i] is None:
        return False
    return (_lower_shadow(bar) >= 2 * abs(_body(bar))
            and _upper_shadow(bar) <= 0.35 * rng
            and bar["close"] < c.sma20[i])


def p_shooting_star(b, c, i):
    bar, rng = b[i], _range(b[i])
    if rng <= 0 or c.sma20[i] is None:
        return False
    return (_upper_shadow(bar) >= 2 * abs(_body(bar))
            and _lower_shadow(bar) <= 0.35 * rng
            and bar["close"] > c.sma20[i])


def p_bull_engulf(b, c, i):
    prev, cur = b[i - 1], b[i]
    return (_body(prev) < 0 and _body(cur) > 0
            and cur["close"] >= prev["open"] and cur["open"] <= prev["close"]
            and abs(_body(cur)) > abs(_body(prev)))


def p_bear_engulf(b, c, i):
    prev, cur = b[i - 1], b[i]
    return (_body(prev) > 0 and _body(cur) < 0
            and cur["close"] <= prev["open"] and cur["open"] >= prev["close"]
            and abs(_body(cur)) > abs(_body(prev)))


def p_morning_star(b, c, i):
    first, mid, last = b[i - 2], b[i - 1], b[i]
    if _body(first) >= 0 or _range(first) <= 0:
        return False
    if abs(_body(mid)) > 0.35 * abs(_body(first)):
        return False
    midpoint = (first["open"] + first["close"]) / 2.0
    return _body(last) > 0 and last["close"] > midpoint


def p_evening_star(b, c, i):
    first, mid, last = b[i - 2], b[i - 1], b[i]
    if _body(first) <= 0 or _range(first) <= 0:
        return False
    if abs(_body(mid)) > 0.35 * abs(_body(first)):
        return False
    midpoint = (first["open"] + first["close"]) / 2.0
    return _body(last) < 0 and last["close"] < midpoint


def p_three_soldiers(b, c, i):
    for k in (i - 2, i - 1, i):
        rng = _range(b[k])
        if rng <= 0 or _body(b[k]) <= 0.5 * rng:
            return False
    return b[i]["close"] > b[i - 1]["close"] > b[i - 2]["close"]


def p_three_crows(b, c, i):
    for k in (i - 2, i - 1, i):
        rng = _range(b[k])
        if rng <= 0 or -_body(b[k]) <= 0.5 * rng:
            return False
    return b[i]["close"] < b[i - 1]["close"] < b[i - 2]["close"]


def p_inside_bar(b, c, i):
    return b[i]["high"] <= b[i - 1]["high"] and b[i]["low"] >= b[i - 1]["low"]


def p_outside_up(b, c, i):
    return (b[i]["high"] > b[i - 1]["high"] and b[i]["low"] < b[i - 1]["low"]
            and _body(b[i]) > 0)


def p_outside_down(b, c, i):
    return (b[i]["high"] > b[i - 1]["high"] and b[i]["low"] < b[i - 1]["low"]
            and _body(b[i]) < 0)


def p_gap_up(b, c, i):
    return b[i]["open"] > b[i - 1]["high"]


def p_gap_down(b, c, i):
    return b[i]["open"] < b[i - 1]["low"]


def p_rsi_oversold(b, c, i):
    return c.rsi14[i] is not None and c.rsi14[i] < 30


def p_rsi_overbought(b, c, i):
    return c.rsi14[i] is not None and c.rsi14[i] > 70


def p_rsi_exit_low(b, c, i):
    a, prev = c.rsi14[i], c.rsi14[i - 1]
    return a is not None and prev is not None and prev <= 30 < a


def p_rsi_exit_high(b, c, i):
    a, prev = c.rsi14[i], c.rsi14[i - 1]
    return a is not None and prev is not None and prev >= 70 > a


def p_macd_bull(b, c, i):
    a, prev = c.macd_h[i], c.macd_h[i - 1]
    return a is not None and prev is not None and prev <= 0 < a


def p_macd_bear(b, c, i):
    a, prev = c.macd_h[i], c.macd_h[i - 1]
    return a is not None and prev is not None and prev >= 0 > a


def p_golden_cross(b, c, i):
    if None in (c.sma50[i], c.sma200[i], c.sma50[i - 1], c.sma200[i - 1]):
        return False
    return c.sma50[i - 1] <= c.sma200[i - 1] and c.sma50[i] > c.sma200[i]


def p_death_cross(b, c, i):
    if None in (c.sma50[i], c.sma200[i], c.sma50[i - 1], c.sma200[i - 1]):
        return False
    return c.sma50[i - 1] >= c.sma200[i - 1] and c.sma50[i] < c.sma200[i]


def p_break20_up(b, c, i):
    window = b[i - 20:i]
    return bool(window) and b[i]["close"] > max(x["high"] for x in window)


def p_break20_down(b, c, i):
    window = b[i - 20:i]
    return bool(window) and b[i]["close"] < min(x["low"] for x in window)


def p_bb_break_up(b, c, i):
    if c.bb_up[i] is None or c.bb_up[i - 1] is None:
        return False
    return b[i]["close"] > c.bb_up[i] and b[i - 1]["close"] <= c.bb_up[i - 1]


def p_bb_break_down(b, c, i):
    if c.bb_low[i] is None or c.bb_low[i - 1] is None:
        return False
    return b[i]["close"] < c.bb_low[i] and b[i - 1]["close"] >= c.bb_low[i - 1]


def p_squeeze(b, c, i):
    """Låg volatilitet kjem før stor rørsle - men seier ikkje kva veg."""
    if c.bb_width[i] is None:
        return False
    window = [w for w in c.bb_width[i - 120:i] if w is not None]
    if len(window) < 60:
        return False
    return c.bb_width[i] <= sorted(window)[int(len(window) * 0.10)]


def p_vol_spike_up(b, c, i):
    if not c.vol20[i]:
        return False
    return b[i]["volume"] > 2.0 * c.vol20[i] and _body(b[i]) > 0


def p_vol_spike_down(b, c, i):
    if not c.vol20[i]:
        return False
    return b[i]["volume"] > 2.0 * c.vol20[i] and _body(b[i]) < 0


# (nøkkel, namn, retning, detektor)
# Retning er kva læreboka påstår. Statistikken får avgjere om ho har rett.
SIGNALS = [
    ("bull_engulf", "Bullish engulfing", "opp", p_bull_engulf),
    ("bear_engulf", "Bearish engulfing", "ned", p_bear_engulf),
    ("hammer", "Hammar", "opp", p_hammer),
    ("shooting_star", "Shooting star", "ned", p_shooting_star),
    ("morning_star", "Morgonstjerne", "opp", p_morning_star),
    ("evening_star", "Aftanstjerne", "ned", p_evening_star),
    ("three_soldiers", "Tre kvite soldatar", "opp", p_three_soldiers),
    ("three_crows", "Tre svarte kråker", "ned", p_three_crows),
    ("doji", "Doji (ubestemt)", "uklar", p_doji),
    ("inside_bar", "Innanfor-bar", "uklar", p_inside_bar),
    ("outside_up", "Utanfor-bar opp", "opp", p_outside_up),
    ("outside_down", "Utanfor-bar ned", "ned", p_outside_down),
    ("gap_up", "Gap opp", "opp", p_gap_up),
    ("gap_down", "Gap ned", "ned", p_gap_down),
    ("rsi_oversold", "RSI under 30", "opp", p_rsi_oversold),
    ("rsi_overbought", "RSI over 70", "ned", p_rsi_overbought),
    ("rsi_exit_low", "RSI kryssar opp over 30", "opp", p_rsi_exit_low),
    ("rsi_exit_high", "RSI kryssar ned under 70", "ned", p_rsi_exit_high),
    ("macd_bull", "MACD kryssar positivt", "opp", p_macd_bull),
    ("macd_bear", "MACD kryssar negativt", "ned", p_macd_bear),
    ("golden_cross", "Gyllent kryss", "opp", p_golden_cross),
    ("death_cross", "Dødskryss", "ned", p_death_cross),
    ("break20_up", "Brot over 20-dagars topp", "opp", p_break20_up),
    ("break20_down", "Brot under 20-dagars botn", "ned", p_break20_down),
    ("bb_break_up", "Ut over øvre Bollinger", "opp", p_bb_break_up),
    ("bb_break_down", "Ut under nedre Bollinger", "ned", p_bb_break_down),
    ("squeeze", "Bollinger-klemme (låg volatilitet)", "uklar", p_squeeze),
    ("vol_spike_up", "Volumspreng opp", "opp", p_vol_spike_up),
    ("vol_spike_down", "Volumspreng ned", "ned", p_vol_spike_down),
]

HORIZONS = (1, 5)


# ---------------------------------------------------------------- statistikken

def _base_rate(closes, horizon, start, stop):
    """Kor ofte stig kursen over denne horisonten på ein tilfeldig dag?

    Dette talet er heile poenget. Ein aksjeindeks stig oftare enn han
    fell, så eit mønster med 55 % treff kan vere DÅRLEGARE enn å kjøpe
    blindt. Utan basisraten ser alt bullish ut.
    """
    ups = total = 0
    for i in range(start, stop):
        if i + horizon >= len(closes):
            break
        total += 1
        if closes[i + horizon] > closes[i]:
            ups += 1
    return (float(ups) / total if total else None), total


def _decluster(hits, min_gap):
    """Eitt utslag per hending, ikkje eitt per dag.

    RSI under 30 held seg gjerne under 30 i ei heil veke. Tel vi kvar
    dag for seg, får vi n=23 der vi eigentleg har fire episodar - og
    fire episodar som overlappar kvarandre sine framtidsvindauge.
    Statistikken blir då ikkje berre litt for optimistisk, han blir
    direkte feil, fordi tilfella ikkje er uavhengige.
    """
    kept = []
    for i in hits:
        if not kept or i - kept[-1] >= min_gap:
            kept.append(i)
    return kept


def _split_half_stable(closes, hits, horizon, base):
    """Held kanten seg i begge halvdelar av historikken?

    Eit mønster som berre verka i 2020 og aldri sidan, er ikkje eit
    mønster - det er ein minnestubb frå ein marknad som ikkje finst
    lenger. Krev vi at forteiknet held seg i begge halvdelane, fell
    dei fleste tilfeldige funna bort av seg sjølve.
    """
    midpoint = len(closes) // 2
    halves = []
    for lo, hi in ((0, midpoint), (midpoint, len(closes))):
        ups = used = 0
        for i in hits:
            if not (lo <= i < hi) or i + horizon >= len(closes):
                continue
            used += 1
            if closes[i + horizon] > closes[i]:
                ups += 1
        if used < 8:
            return False  # For tynt i den eine halvdelen til å seie noko.
        halves.append(float(ups) / used - base)
    return (halves[0] > 0) == (halves[1] > 0)


def _measure(closes, hits, horizon, base):
    # Ikkje-overlappande vindauge: to utslag nærare enn horisonten deler
    # framtid, og då tel vi den same rørsla to gonger.
    hits = _decluster(hits, max(horizon, 3))

    ups = 0
    moves = []
    used = 0
    for i in hits:
        if i + horizon >= len(closes):
            continue
        used += 1
        change = closes[i + horizon] / closes[i] - 1.0
        moves.append(change)
        if change > 0:
            ups += 1
    if used < MIN_SAMPLE or base is None:
        return {"n": used, "enough": False}

    hit_rate = float(ups) / used
    edge = hit_rate - base
    # Standardfeil under nullhypotesen "mønsterdagar oppfører seg som
    # alle andre dagar". Er kanten mindre enn to av desse, har vi
    # ingenting - same kor forlokkande prosenten ser ut.
    se = math.sqrt(base * (1 - base) / used)
    z = edge / se if se > 0 else 0.0
    strong = abs(z) >= STRONG_Z
    stable = _split_half_stable(closes, hits, horizon, base) if strong else False
    return {
        "n": used,
        "enough": True,
        "hit_rate": hit_rate,
        "base": base,
        "edge": edge,
        "z": z,
        "significant": abs(z) >= SIGNIFICANT_Z,
        "strong": strong,
        "stable": stable,
        # Berre dette flagget får lov til å flytte ei avgjerd: sterk nok
        # til å overleve at vi testa 174 ting, og stabil over tid.
        "trustworthy": strong and stable,
        "avg_move": sum(moves) / len(moves),
    }


def _scan(bars, ctx, detector):
    hits = []
    for i in range(WARMUP, len(bars)):
        try:
            if detector(bars, ctx, i):
                hits.append(i)
        except (TypeError, IndexError, ZeroDivisionError):
            continue
    return hits


# ------------------------------------------------------------------- regime

def _regime(bars, ctx):
    i = len(bars) - 1
    bar = bars[i]
    close = bar["close"]
    out = {
        "date": bar["date"],
        "close": close,
        "change_pct": None,
        "rsi": ctx.rsi14[i],
        "macd_hist": ctx.macd_h[i],
        "atr_pct": (ctx.atr14[i] / close * 100.0) if ctx.atr14[i] else None,
        "trend": "ukjend",
        "above": [],
        "pct_b": None,
        "from_high20": None,
        "from_low20": None,
        "vol_vs_avg": None,
    }
    if i > 0 and bars[i - 1]["close"]:
        out["change_pct"] = (close / bars[i - 1]["close"] - 1.0) * 100.0

    for name, series in (("SMA20", ctx.sma20), ("SMA50", ctx.sma50), ("SMA200", ctx.sma200)):
        if series[i] is not None and close > series[i]:
            out["above"].append(name)

    if ctx.sma50[i] is not None and ctx.sma200[i] is not None:
        if close > ctx.sma50[i] > ctx.sma200[i]:
            out["trend"] = "opptrend"
        elif close < ctx.sma50[i] < ctx.sma200[i]:
            out["trend"] = "nedtrend"
        else:
            out["trend"] = "sidelengs / blanda"

    if None not in (ctx.bb_up[i], ctx.bb_low[i]) and ctx.bb_up[i] != ctx.bb_low[i]:
        out["pct_b"] = (close - ctx.bb_low[i]) / (ctx.bb_up[i] - ctx.bb_low[i])

    window = bars[max(0, i - 20):i + 1]
    high20 = max(x["high"] for x in window)
    low20 = min(x["low"] for x in window)
    out["from_high20"] = (close / high20 - 1.0) * 100.0
    out["from_low20"] = (close / low20 - 1.0) * 100.0

    if ctx.vol20[i]:
        out["vol_vs_avg"] = bar["volume"] / ctx.vol20[i]

    return out


def analyse(bars, label):
    """Les chartet og tel opp historikken bak det som står der no."""
    if not bars or len(bars) < WARMUP + 60:
        return None

    ctx = Context(bars)
    closes = ctx.closes
    last = len(bars) - 1

    bases = {}
    for horizon in HORIZONS:
        bases[horizon] = _base_rate(closes, horizon, WARMUP, len(closes))

    fired = []
    for key, name, direction, detector in SIGNALS:
        try:
            if not detector(bars, ctx, last):
                continue
        except (TypeError, IndexError, ZeroDivisionError):
            continue

        hits = _scan(bars, ctx, detector)
        entry = {
            "key": key, "name": name, "direction": direction,
            "occurrences": len(hits), "stats": {},
        }
        for horizon in HORIZONS:
            base, _ = bases[horizon]
            entry["stats"][horizon] = _measure(closes, hits, horizon, base)
        fired.append(entry)

    return {
        "label": label,
        "bars": len(bars),
        "regime": _regime(bars, ctx),
        "base_rates": dict((h, bases[h][0]) for h in HORIZONS),
        "signals": fired,
    }


# -------------------------------------------------------------- presentasjon

def _pct(value, digits=0):
    if value is None:
        return "?"
    return ("%." + str(digits) + "f %%") % (value * 100.0)


def format_report(report):
    """Kompakt nok til å sende, detaljert nok til å ikkje lyge."""
    if not report:
        return ""

    reg = report["regime"]
    lines = []
    change = ("%+.2f %%" % reg["change_pct"]) if reg["change_pct"] is not None else "?"
    lines.append("%s - siste ferdige dag %s, slutt %.2f (%s)" % (
        report["label"], reg["date"], reg["close"], change))

    over = ", ".join(reg["above"]) if reg["above"] else "ingen"
    lines.append("  Trend: %s | over %s" % (reg["trend"], over))

    bits = []
    if reg["rsi"] is not None:
        bits.append("RSI %.0f" % reg["rsi"])
    if reg["macd_hist"] is not None:
        bits.append("MACD-hist %+.2f" % reg["macd_hist"])
    if reg["atr_pct"] is not None:
        bits.append("ATR %.1f %%" % reg["atr_pct"])
    if reg["pct_b"] is not None:
        bits.append("Bollinger %%B %.2f" % reg["pct_b"])
    if reg["vol_vs_avg"] is not None:
        bits.append("volum %.1fx snitt" % reg["vol_vs_avg"])
    if bits:
        lines.append("  " + " | ".join(bits))

    lines.append("  Avstand: %.1f %% frå 20-dagars topp, %+.1f %% frå 20-dagars botn" % (
        reg["from_high20"], reg["from_low20"]))

    base_txt = ", ".join(
        "%d dag%s %s" % (h, "" if h == 1 else "ar", _pct(report["base_rates"][h]))
        for h in HORIZONS)
    lines.append("  Basisrate (kor ofte det stig uansett): %s" % base_txt)

    if not report["signals"]:
        lines.append("  Mønster i går: ingen av dei 29 slo ut")
        return "\n".join(lines)

    lines.append("  Mønster i går:")
    for sig in report["signals"]:
        lines.append("    %s [lærebok: %s], %d tilfelle i historikken" % (
            sig["name"], sig["direction"], sig["occurrences"]))
        for horizon in HORIZONS:
            st = sig["stats"][horizon]
            unit = "dag" if horizon == 1 else "dagar"
            if not st.get("enough"):
                lines.append("      %d %s: berre %d tilfelle - for lite til å seie noko"
                             % (horizon, unit, st["n"]))
                continue
            if st["trustworthy"]:
                verdict = "STERK OG STABIL"
            elif st["strong"]:
                verdict = "sterk, men held seg ikkje over tid"
            elif st["significant"]:
                verdict = "svak - ventar vi 9 slike av rein flaks"
            else:
                verdict = "innanfor støy"
            lines.append(
                "      %d %s: %s opp (n=%d) mot basis %s | kant %+.1f pp | z=%+.1f %s"
                % (horizon, unit, _pct(st["hit_rate"]), st["n"], _pct(st["base"]),
                   st["edge"] * 100.0, st["z"], verdict))
    return "\n".join(lines)


TECHNICAL_CAVEAT = (
    "Om tala over: n er talet på GONGER mønsteret har oppstått, ikkje talet på "
    "dagar - utslag som klumpar seg saman er slåtte i hop, og vindauga overlappar "
    "ikkje. 'basis' er kor ofte kursen stig uansett, og han er over 50 %% for "
    "aksjar, så eit mønster med 55 %% treff er DÅRLEGARE enn ingenting. Vi testar "
    "%d kombinasjonar, så rundt 9 av dei vil vise z over 2 av rein flaks. Berre "
    "linjer merkte STERK OG STABIL har overlevd både eit strengare krav og ein "
    "test på om kanten held seg i begge halvdelar av historikken. Alt anna skal "
    "du lese som 'ingen informasjon'." % TESTS_RUN
)


def strongest_edge(reports):
    """Den einaste tekniske observasjonen som fortener å telje.

    Returnerer (retning, z, tekst) for det signalet med størst kant som
    er både sterk og stabil - eller None dersom ingen av dei kom over
    grensa. Det siste er det normale, og det er meininga.

    Merk at retninga blir lesen ut av STATISTIKKEN, ikkje ut av
    læreboka. Fleire mønster i olje peikar motsett veg av det dei skal
    ifølgje teorien, og då er det historikken som gjeld.
    """
    best = None
    for report in reports:
        if not report:
            continue
        for sig in report["signals"]:
            for horizon in HORIZONS:
                st = sig["stats"][horizon]
                if not st.get("enough") or not st.get("trustworthy"):
                    continue
                observed = "opp" if st["edge"] > 0 else "ned"
                if best is None or abs(st["z"]) > abs(best[1]):
                    note = ""
                    if sig["direction"] in ("opp", "ned") and sig["direction"] != observed:
                        note = " (MOTSETT av læreboka - historikken vinn)"
                    best = (
                        observed,
                        st["z"],
                        "%s i %s: %s opp mot basis %s over %d dag(ar), n=%d, z=%+.1f%s" % (
                            sig["name"], report["label"], _pct(st["hit_rate"]),
                            _pct(st["base"]), horizon, st["n"], st["z"], note),
                    )
    return best


# ------------------------------------------------------------ gap-statistikk

# Bøttene er valde slik at kvar av dei har nok dagar til å seie noko,
# og slik at grensene ligg der ei rørsle byrjar å bety noko praktisk.
GAP_BUCKETS = [
    (-99.0, -1.0, "under -1 %"),
    (-1.0, -0.3, "-1 % til -0,3 %"),
    (-0.3, 0.3, "flatt"),
    (0.3, 1.0, "+0,3 % til +1 %"),
    (1.0, 99.0, "over +1 %"),
]


def gap_statistics(bars):
    """Kva ei rørsle over natta faktisk seier om dagen.

    Dette er den viktigaste tabellen i heile verktøyet, fordi han skil
    to ting som ser like ut og ikkje er det:

      "dagen enda opp"      - målt frå går-slutt til i dag-slutt
      "det gjekk vidare opp" - målt frå OPNINGA til slutt

    Etter eit gap opp over 1 % endar 88 % av dagane høgare enn dagen før.
    Det ser ut som eit fantastisk signal. Det er ikkje eit signal i det
    heile - det er aritmetikk. Gapet har alt skjedd før du kan handle på
    det. Frå opninga og utover er treffprosenten 59 %, altså nesten
    nøyaktig basisraten.

    Så: rørsla over natta fortel deg kvar marknaden OPNAR. Ho fortel deg
    ingenting om kva han gjer etterpå. Blandar du dei to saman, får du
    eit verktøy som verkar treffsikkert og er verdilaust.
    """
    if not bars or len(bars) < 200:
        return None

    rows = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1]["close"]
        opening = bars[i]["open"]
        closing = bars[i]["close"]
        if not prev_close or not opening:
            continue
        rows.append((
            (opening / prev_close - 1.0) * 100.0,   # gapet
            closing > opening,                       # vidare opp frå opning
            closing > prev_close,                    # dagen totalt opp
        ))
    if not rows:
        return None

    base = sum(1 for r in rows if r[1]) / float(len(rows))

    buckets = []
    for low, high, label in GAP_BUCKETS:
        subset = [r for r in rows if low <= r[0] < high]
        if len(subset) < 25:
            continue
        n = float(len(subset))
        buckets.append({
            "label": label, "low": low, "high": high, "n": int(n),
            "further_up": sum(1 for r in subset if r[1]) / n,
            "day_up": sum(1 for r in subset if r[2]) / n,
        })
    return {"base": base, "buckets": buckets, "n": len(rows)}


def gap_context(stats, current_move_pct, label):
    """Kva den faktiske rørsla i natt tyder, med tal bak."""
    if not stats or current_move_pct is None:
        return ""

    match = None
    for bucket in stats["buckets"]:
        if bucket["low"] <= current_move_pct < bucket["high"]:
            match = bucket
            break
    if match is None:
        return ""

    retning = "opp" if current_move_pct >= 0 else "ned"
    return (
        "%s: rører seg %+.2f %% no (bøtta '%s', %d liknande dagar i historikken).\n"
        "  Marknaden opnar truleg %s - det er alt i prisen.\n"
        "  Men frå OPNINGA og utover gjekk det opp %.0f %% av gongene, mot "
        "basis %.0f %%. Rørsla i natt seier altså lite om resten av dagen."
    ) % (label, current_move_pct, match["label"], match["n"], retning,
         match["further_up"] * 100.0, stats["base"] * 100.0)
