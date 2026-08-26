"""Dagleg OHLC-historikk, gratis og utan API-nøkkel.

Kjelda er api.nasdaq.com sitt opne historikk-endepunkt. Det gir ~1900
handledagar med open, high, low, close og volum - nok til å rekne
statistikk på lysestake-mønster i staden for å berre påstå at dei verkar.

Kvifor ETF-ar og ikkje indeksar: endepunktet har ikkje indeksar, og ETF-ar
er dessutan betre til dette. Ein indeks har ikkje volum. QQQ, USO og BNO
har ekte omsetnad, og volum er halve poenget med eit lysestake-mønster.

Historikken blir lagra på disk og henta på nytt éin gong i døgnet. Ein
dagsbar endrar seg ikkje, så å hente 1900 av dei kvart 20. minutt ville
vore både treigt og uhøfleg.
"""

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT / "cache"

URL = "https://api.nasdaq.com/api/quote/%s/historical"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Ein dagsbar er ferdig når dagen er ferdig. 18 timar gjer at vi hentar
# éin gong per morgon og lever på det resten av dagen.
CACHE_TTL_SECONDS = 18 * 3600


def _num(value):
    """'$208.48' og '135,187,300' skal begge bli tal."""
    if value is None:
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in ("--", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_rows(rows):
    """Nasdaq leverer nyaste fyrst. Alt nedanfor reknar med eldste fyrst."""
    bars = []
    for row in rows:
        bar = {
            "date": row.get("date", ""),
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": _num(row.get("close")),
            "volume": _num(row.get("volume")) or 0.0,
        }
        if None in (bar["open"], bar["high"], bar["low"], bar["close"]):
            continue
        if bar["high"] < bar["low"] or bar["close"] <= 0:
            continue
        bars.append(bar)
    bars.reverse()
    return bars


def _cache_path(symbol):
    safe = "".join(ch for ch in symbol if ch.isalnum())
    return CACHE_DIR / ("hist_%s.json" % safe)


def _read_cache(symbol, max_age):
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (ValueError, OSError):
        return None
    if time.time() - payload.get("fetched_at", 0) > max_age:
        return None
    return payload.get("bars") or None


def _write_cache(symbol, bars):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        with open(_cache_path(symbol), "w", encoding="utf-8") as fh:
            json.dump({"fetched_at": time.time(), "bars": bars}, fh)
    except OSError:
        pass  # Cache er ein bonus, ikkje eit krav.


def _stale_cache(symbol):
    """Gammal cache slår ingen data i det heile.

    Ein historikk som er ei veke gammal er framleis 1900 dagar med
    mønster. Berre siste baren manglar, og då fell vi tilbake til å
    rekne utan det ferskaste - ikkje til å rekne ingenting.
    """
    return _read_cache(symbol, max_age=30 * 24 * 3600)


def fetch_daily(symbol, assetclass="etf", years=8, timeout=30):
    """Returnerer liste med dagsbarar, eldste fyrst. Tom liste ved feil."""
    cached = _read_cache(symbol, CACHE_TTL_SECONDS)
    if cached:
        return cached

    today = time.strftime("%Y-%m-%d")
    start = time.strftime("%Y-%m-%d", time.localtime(time.time() - years * 365.25 * 86400))
    try:
        resp = requests.get(
            URL % symbol,
            params={
                "assetclass": assetclass,
                "fromdate": start,
                "todate": today,
                "limit": 9999,
            },
            headers=HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return _stale_cache(symbol) or []

    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    bars = _parse_rows(rows)
    if len(bars) < 60:
        # For lite til å rekne noko fornuftig ut av.
        return _stale_cache(symbol) or []

    _write_cache(symbol, bars)
    return bars


def fetch_many(specs, workers=4):
    """specs: {key: {"symbol": .., "assetclass": ..}} -> {key: [bar, ...]}"""
    import concurrent.futures

    def one(pair):
        key, spec = pair
        return key, fetch_daily(
            spec.get("symbol", key),
            spec.get("assetclass", "etf"),
        )

    out = {}
    if not specs:
        return out
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for key, bars in pool.map(one, list(specs.items())):
            out[key] = bars
    return out
