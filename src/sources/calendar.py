"""Kva som er PLANLAGT i dag.

Dette er den einaste kjelda i heile verktøyet som ikkje er gjetting.

Ei nyheit må tolkast: er ho ny, er ho alt prisa inn, er ho i det heile
sann? Ein kalender må ikkje tolkast. Core PCE kjem klokka 14:30 norsk
tid med konsensus 0,2 %, og Nvidia rapporterer etter stenging. Det er
fakta, kjende på førehand, om hendingar som beviseleg flyttar marknaden.

To ting følgjer av det:

  - Veit vi at eit stort tal kjem om to timar, skal vi vere MEIR
    tilbakehaldne, ikkje mindre. Å rope "opp" rett før CPI er å gjette
    på ein terning som ikkje er kasta enno.

  - Veit vi at det IKKJE står noko på kalenderen, er det eit argument
    for at ein roleg dag faktisk er roleg, og ikkje berre stille før
    noko vi ikkje har fått med oss.

Kjelda er api.nasdaq.com, same som historikken. Gratis, utan nøkkel.
"""

import concurrent.futures

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

ECONOMIC_URL = "https://api.nasdaq.com/api/calendar/economicevents"
EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Kalenderen har 58 rader i døgnet. Dei aller fleste er ting som
# Singapore industriproduksjon, som ikkje flyttar Nasdaq eller olje ei
# krone. Dette er lista over dei som gjer det.
HIGH_IMPACT = [
    # Inflasjon - det som styrer renta, og dermed vekstaksjane
    "cpi", "core cpi", "pce", "core pce", "ppi", "inflation rate",
    # Arbeidsmarknad
    "nonfarm payrolls", "unemployment rate", "initial jobless claims",
    "adp employment", "average hourly earnings", "jolts",
    # Vekst og aktivitet
    "gdp", "retail sales", "ism manufacturing", "ism services",
    "ism non-manufacturing", "durable goods", "industrial production",
    "consumer confidence", "michigan", "pmi",
    # Sentralbank - det tyngste av alt
    "fed interest rate", "fomc", "interest rate decision", "rate decision",
    "fed chair", "powell", "beige book", "ecb", "boe", "boj",
    # Olje - desse flyttar oljeprisen direkte og på minuttet
    "crude oil inventories", "eia", "api weekly", "opec",
    "natural gas storage", "baker hughes", "rig count",
]

# Land som betyr noko for Nasdaq og olje. Resten er bakgrunnsstøy.
RELEVANT_COUNTRIES = [
    "united states", "euro zone", "eurozone", "china",
    "united kingdom", "germany", "japan", "saudi arabia", "russia",
]

# Selskap som er store nok til å flytte heile indeksen aleine, pluss
# oljeselskapa. Nvidia er over 5000 milliardar dollar - eit resultat
# derifrå ER ei makrohending for Nasdaq.
MEGA_CAP_USD = 300e9
ALWAYS_WATCH = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA",
    "AVGO", "AMD", "MU", "INTC", "TSM", "ASML", "SMCI", "ORCL",
    "XOM", "CVX", "COP", "SLB", "OXY",
]


def _to_oslo(time_et, tzname="Europe/Oslo"):
    """Kalenderen oppgir tid i New York. Brukaren bur i Noreg.

    Skiljet er 6 timar om sommaren og 5 om vinteren, og dei to
    landa byter ikkje same helga. Difor konverterer vi ordentleg i
    staden for å leggje til eit fast tal.
    """
    if not time_et or ZoneInfo is None:
        return time_et
    try:
        hour, minute = [int(x) for x in str(time_et).split(":")[:2]]
    except (ValueError, IndexError):
        return time_et
    from datetime import datetime
    try:
        naive = datetime.now(ZoneInfo("America/New_York")).replace(
            hour=hour, minute=minute, second=0, microsecond=0)
        return naive.astimezone(ZoneInfo(tzname)).strftime("%H:%M")
    except Exception:
        return time_et


def _clean(value):
    """Nasdaq skriv &nbsp; der det ikkje finst noko tal.

    Utan dette blir 'ikkje sleppt enno' lese som 'sleppt, verdi &nbsp;',
    og då snur heile tolkinga: verktøyet ville trudd at CPI-talet alt
    var kjent når det i røynda kjem om fire timar.
    """
    text = str(value or "")
    for entity in ("&nbsp;", "\xa0", "&amp;", "--", "N/A"):
        text = text.replace(entity, " ")
    return text.strip()


def _get(url, date, timeout=20):
    try:
        resp = requests.get(url, params={"date": date}, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return []
    return ((payload.get("data") or {}).get("rows")) or []


def _is_high_impact(name):
    lowered = (name or "").lower()
    return any(word in lowered for word in HIGH_IMPACT)


def fetch_economic(date, tzname="Europe/Oslo"):
    """Dei planlagde tala som faktisk flyttar noko."""
    events = []
    seen = set()
    for row in _get(ECONOMIC_URL, date):
        name = row.get("eventName") or ""
        country = (row.get("country") or "").lower()
        if not _is_high_impact(name):
            continue
        if not any(c in country for c in RELEVANT_COUNTRIES):
            continue

        # Same tal blir ofte lista to gonger (månad og år). Vi vil ha
        # begge dersom dei har ulike verdiar, men ikkje reine dublettar.
        key = (row.get("gmt"), name, row.get("consensus"), row.get("previous"))
        if key in seen:
            continue
        seen.add(key)

        # Same tal kjem i fleire utgåver: månadsvekst, årsvekst, indeks.
        # To av dei seier alt; elleve av dei druknar resten av dagen.
        base = name.lower().strip()
        variants = sum(1 for e in events if e["name"].lower().strip() == base)
        if variants >= 2:
            continue

        events.append({
            "time_et": row.get("gmt") or "",
            "time_local": _to_oslo(row.get("gmt"), tzname),
            "country": row.get("country") or "",
            "name": name,
            "actual": _clean(row.get("actual")),
            "consensus": _clean(row.get("consensus")),
            "previous": _clean(row.get("previous")),
        })
    events.sort(key=lambda e: (_priority(e["name"]), e["time_et"]))
    return events


# Elleve PCE-liner klokka 14:30 skuvar EIA-lagertala klokka 16:30 ut av
# prompten, og det er nettopp dei som flyttar oljeprisen. Difor sorterer
# vi på kor tungt tale veg fyrst, og på klokka etterpå.
_TOP = ("fomc", "fed interest rate", "interest rate decision", "rate decision",
        "core pce", "core cpi", "nonfarm payrolls", "crude oil inventories",
        "opec", "powell", "fed chair")
_MID = ("cpi", "pce", "ppi", "gdp", "retail sales", "ism", "unemployment rate",
        "initial jobless claims", "eia", "adp employment")


def _priority(name):
    lowered = (name or "").lower()
    if any(word in lowered for word in _TOP):
        return 0
    if any(word in lowered for word in _MID):
        return 1
    return 2


def _market_cap(row):
    try:
        return float(str(row.get("marketCap") or "0").replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def fetch_earnings(date):
    """Berre selskap store nok til å dra indeksen etter seg."""
    out = []
    for row in _get(EARNINGS_URL, date):
        symbol = (row.get("symbol") or "").upper()
        if symbol not in ALWAYS_WATCH and _market_cap(row) < MEGA_CAP_USD:
            continue
        when = (row.get("time") or "").replace("time-", "").replace("-", " ")
        out.append({
            "symbol": symbol,
            "name": row.get("name") or symbol,
            "when": when or "ukjend tidspunkt",
            "market_cap": _market_cap(row),
            "eps_forecast": _clean(row.get("epsForecast")),
        })
    out.sort(key=lambda e: e["market_cap"], reverse=True)
    return out


def fetch_today(date, tzname="Europe/Oslo"):
    """Berre I DAG.

    Endepunktet ser ut til å svare med neste handledag for kvar dato
    som ligg fram i tid: ber du om i morgon, får du i dag sine tal
    tilbake utan at noko seier ifrå. Ein kalender som stille flyttar
    hendingar ein dag er verre enn ingen kalender, så vi spør berre om
    den datoen vi veit vi får rett svar på.
    """
    return {
        "economic": fetch_economic(date, tzname),
        "earnings": fetch_earnings(date),
    }


# Ein prompt med 20 kalenderlinjer druknar nyheitene. Dei viktigaste
# står fyrst uansett, fordi lista er sortert på klokkeslett og dei
# store amerikanske tala kjem tidleg.
MAX_EVENTS = 12


def format_calendar(entry):
    """Kompakt kalender til prompten."""
    if not entry:
        return "Ingen kalenderdata."

    econ = entry.get("economic") or []
    earn = entry.get("earnings") or []
    if not econ and not earn:
        return ("Ingenting stort står på kalenderen i dag. Ein roleg dag er "
                "då truleg berre roleg.")

    lines = []
    venter = 0
    # Vel dei viktigaste, men vis dei i klokkerekkjefølgje - ein kalender
    # som hoppar fram og tilbake i tid er vond å lese.
    valde = sorted(econ[:MAX_EVENTS], key=lambda e: e["time_et"])
    for event in valde:
        if event["actual"]:
            lines.append("  %s %s: %s = %s (venta %s, førre %s)  ALT SLEPPT" % (
                event["time_local"], event["country"], event["name"],
                event["actual"], event["consensus"] or "?", event["previous"] or "?"))
        else:
            venter += 1
            lines.append("  %s %s: %s (venta %s, førre %s)  IKKJE SLEPPT ENNO" % (
                event["time_local"], event["country"], event["name"],
                event["consensus"] or "?", event["previous"] or "?"))

    if len(econ) > MAX_EVENTS:
        lines.append("  ... og %d mindre tal til" % (len(econ) - MAX_EVENTS))

    for company in earn[:6]:
        lines.append("  Resultat %s (%s), %s - venta EPS %s" % (
            company["symbol"], company["name"][:30],
            company["when"], company["eps_forecast"] or "?"))

    if venter:
        lines.append("  MERK: %d av tala over er IKKJE sleppte enno. Retninga "
                     "deira er ukjend for alle." % venter)
    return "\n".join(lines)


def pending_count(entry):
    """Kor mange store tal som framleis ligg ute i dag.

    Dette er den viktigaste enkeltopplysninga verktøyet har. Ligg det
    eit CPI-tal ute om to timar, skal ingen påstand om retning kunne
    få høg confidence - uansett kor pen resten av analysen er.
    """
    if not entry:
        return 0, []
    waiting = [e for e in (entry.get("economic") or []) if not e["actual"]]
    return len(waiting), waiting
