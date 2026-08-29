"""Historiske nyheiter, så simuleringar kan bli ærlege.

Dette blir ikkje brukt i drift. Det finst berre for at spørsmålet Sondre
stilte skal kunne svarast på: "koffor må eg tape penger først".

Utan dette kunne vi berre teste den halvdelen av verktøyet som les chart
og kalender - og den halvdelen sa vi alt visste var verdilaus. All
sikkerheita modellen har, kjem frå nyheitene. Ein simulering utan dei
måler difor ingenting: han seier "uklart" kvar einaste dag, med snitt
29 % confidence mot ein terskel på 58.

GDELT er eit ope arkiv over global nyheitsdekning. Gratis, ingen nøkkel,
og det går att i tid. Det gjer at ein kan spørje: kva stod i avisene den
10. juni 2026 om morgonen - og så gi modellen nøyaktig det, og
samanlikne med kva som faktisk hende.

Merk kva dette IKKJE er: det er ikkje same utval som feed-lista vår, og
GDELT rangerer etter sin eigen relevans. Ein simulering med desse
overskriftene er difor ei tilnærming, ikkje ein perfekt rekonstruksjon.
Men det er uendeleg mykje nærare enn å teste utan nyheiter i det heile.
"""

import requests

URL = "https://api.gdeltproject.org/api/v2/doc/doc"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# Det same spørsmålet kvar gong, så ingen dag får eit meir gunstig utval
# enn ein annan. Endrar ein dette midt i ein test, samanliknar ein
# epler og pærer utan å merke det.
SPØRRING = ('(nasdaq OR "federal reserve" OR inflation OR CPI OR '
            '"stock market" OR nvidia OR "interest rate" OR earnings) '
            'sourcecountry:US')

# Kjelder vi kjenner att frå feed-lista, så tier-merkinga blir den same
# som i drift.
PRIMÆR = ("federalreserve.gov", "bls.gov", "ecb.europa.eu", "eia.gov")
BYRÅ = ("reuters.com", "bloomberg.com", "apnews.com", "wsj.com", "ft.com",
        "cnbc.com", "bbc.com", "bbc.co.uk", "nytimes.com", "marketwatch.com")
LAUSE = ("finance.yahoo.com", "benzinga.com", "seekingalpha.com",
         "investing.com", "zerohedge.com", "fool.com")


def _tier(domene):
    d = (domene or "").lower()
    if any(p in d for p in PRIMÆR):
        return "primary"
    if any(p in d for p in BYRÅ):
        return "wire"
    if any(p in d for p in LAUSE):
        return "loose"
    return "normal"


def hent(dato_iso, frå_time=4, til_time=13, maks=25, timeout=60):
    """Overskrifter frå ein historisk dag, i same form som news.fetch_all.

    Vindauget 04-13 UTC er valt med vilje: det er natta og morgonen fram
    til rett før den amerikanske opninga. Alt seinare ville vore å la
    modellen sjå reaksjonen han skal spå.
    """
    dag = dato_iso.replace("-", "")
    try:
        resp = requests.get(
            URL,
            params={
                "query": SPØRRING,
                "mode": "artlist",
                "format": "json",
                "maxrecords": maks,
                "sort": "hybridrel",
                "startdatetime": "%s%02d0000" % (dag, frå_time),
                "enddatetime": "%s%02d0000" % (dag, til_time),
            },
            headers=HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        artiklar = resp.json().get("articles") or []
    except (requests.RequestException, ValueError):
        return []

    ut = []
    sett = set()
    for a in artiklar:
        tittel = (a.get("title") or "").strip()
        if not tittel or len(tittel) < 20:
            continue
        # GDELT set mellomrom rundt teiknsetjing: "4 . 2 %" -> "4.2 %"
        tittel = tittel.replace(" . ", ".").replace(" , ", ", ").replace(" %", " %")
        nykel = tittel.lower()[:60]
        if nykel in sett:
            continue
        sett.add(nykel)
        domene = a.get("domain", "")
        ut.append({
            "source": domene,
            "tier": _tier(domene),
            "title": tittel,
            "summary": "",
            "age_hours": 3,
            "source_count": 1,
            "assets": ["nasdaq"],
            "rule_score": 20,
        })
    return ut[:12]
