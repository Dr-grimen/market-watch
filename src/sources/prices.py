"""Hentar prisar frå gratis kjelder, utan API-nøkkel.

Primærkjelde er CNBC sitt opne quote-endepunkt: det gir alle tickerane i
eitt kall og fungerer også frå datasenter-IP-ar (som GitHub Actions har).
Yahoo Finance ligg som reserve — det svarer ofte 429 på delte IP-ar, så
det er med som backup, ikkje som hovudveg.
"""

import requests

CNBC_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def _to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("+", ""))
    except ValueError:
        return None


def fetch_cnbc(symbols, timeout=20):
    """Eitt kall for alle symbol. Returnerer {symbol: quote}."""
    try:
        resp = requests.get(
            CNBC_URL,
            params={
                "symbols": "|".join(symbols),
                "requestMethod": "itv",
                "noform": "1",
                "partnerId": "2",
                "fund": "1",
                "exthrs": "1",
                "output": "json",
                "events": "1",
            },
            headers=HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return {}

    quotes = data.get("FormattedQuoteResult", {}).get("FormattedQuote", [])
    if isinstance(quotes, dict):
        quotes = [quotes]

    out = {}
    for raw in quotes:
        symbol = raw.get("symbol")
        last = _to_float(raw.get("last"))
        prev = _to_float(raw.get("previous_day_closing"))
        if not symbol or last is None:
            continue

        change_pct = _to_float(raw.get("change_pct"))
        if change_pct is None and prev:
            change_pct = (last - prev) / prev * 100.0
        if change_pct is None:
            continue
        # change_pct kjem utan forteikn i strengen når han er negativ,
        # så vi les forteiknet frå sjølve endringa.
        change = _to_float(raw.get("change"))
        if change is not None and change < 0:
            change_pct = -abs(change_pct)

        out[symbol] = {
            "ticker": symbol,
            "name": raw.get("name") or symbol,
            "price": round(last, 2),
            "previous_close": round(prev, 2) if prev else None,
            "change_pct": round(change_pct, 2),
            "market_state": raw.get("curmktstatus", ""),
        }
    return out


def fetch_yahoo(ticker, timeout=15):
    """Reserve. Yahoo rate-limitar hardt, så feil her er venta."""
    try:
        resp = requests.get(
            YAHOO_URL.format(ticker=ticker),
            params={"range": "2d", "interval": "5m", "includePrePost": "true"},
            headers=HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None

    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None or not prev:
        return None

    return {
        "ticker": ticker,
        "name": meta.get("shortName") or ticker,
        "price": round(float(price), 2),
        "previous_close": round(float(prev), 2),
        "change_pct": round((price - prev) / prev * 100.0, 2),
        "market_state": meta.get("marketState", ""),
    }


def fetch_all(assets):
    """assets: dict frå config. Returnerer {asset_key: [quote, ...]}."""
    wanted = []
    for spec in assets.values():
        for ticker in spec.get("tickers", []):
            if ticker not in wanted:
                wanted.append(ticker)

    cnbc = fetch_cnbc(wanted) if wanted else {}

    out = {}
    for key, spec in assets.items():
        quotes = []
        for ticker in spec.get("tickers", []):
            quote = cnbc.get(ticker)
            if quote is None:
                fallback = spec.get("yahoo_fallback", {}).get(ticker)
                if fallback:
                    quote = fetch_yahoo(fallback)
            if quote:
                quotes.append(quote)
        out[key] = quotes
    return out


def summarize(quotes):
    """Kort tekstlinje til bruk i prompt og varsel."""
    parts = []
    for q in quotes:
        sign = "+" if q["change_pct"] >= 0 else ""
        parts.append("%s %s%s%%" % (q["name"], sign, q["change_pct"]))
    return ", ".join(parts)


def summarize_grouped(quotes_by_group, groups_config):
    """Verdsbiletet, gruppert og lesbart.

    Ei flat rekkje med 18 tal er vanskeleg å lese noko ut av - verken
    for eit menneske eller for ein språkmodell. Grupperinga gjer at
    'Asia opp, Europa ned' kjem fram som eit mønster i staden for å
    drukne mellom valutakryss.
    """
    blokker = []
    for key, spec in groups_config.items():
        quotes = quotes_by_group.get(key) or []
        if not quotes:
            continue
        blokker.append("%s: %s" % (spec.get("label", key), summarize(quotes)))
    return "\n".join(blokker)


def biggest_movers(quotes, minimum_pct=1.0, limit=5):
    """Dei som faktisk rører på seg. Resten er støy."""
    movers = [q for q in quotes if abs(q.get("change_pct", 0)) >= minimum_pct]
    movers.sort(key=lambda q: abs(q["change_pct"]), reverse=True)
    return movers[:limit]
