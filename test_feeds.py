"""Testar kandidatkjelder live. Berre dei som svarer med ferske saker
blir lagt inn i config.yaml.

Bruk:  .venv/bin/python test_feeds.py
"""

import concurrent.futures
import sys

import feedparser
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

GN = ("https://news.google.com/rss/search?q=%s&hl=en-US&gl=US&ceid=US:en")

KANDIDATAR = [
    # --- Asia ---
    ("Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar"),
    ("SCMP Business", "https://www.scmp.com/rss/92/feed"),
    ("Japan Times Business", "https://www.japantimes.co.jp/feed/topstories/"),
    ("CNA Business", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936"),
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Korea Herald Business", "http://www.koreaherald.com/rss/020000000000.xml"),

    # --- Midtausten og olje-geografi ---
    ("Arab News Business", "https://www.arabnews.com/cat/3/feed"),
    ("Al Arabiya Business", "https://english.alarabiya.net/tools/rss/business.xml"),
    ("Middle East Eye", "https://www.middleeasteye.net/rss"),

    # --- Energi ---
    ("Oil & Gas Journal", "https://www.ogj.com/rss/all-content"),
    ("World Oil", "https://worldoil.com/rss/news"),
    ("Upstream Online", "https://www.upstreamonline.com/rss"),
    ("Offshore Energy", "https://www.offshore-energy.biz/feed/"),
    ("Natural Gas Intel", "https://www.naturalgasintel.com/feed/"),
    ("Energy Voice", "https://www.energyvoice.com/feed/"),
    ("IEA News", "https://www.iea.org/rss/news"),
    ("Reuters Energy GN", GN % "when:6h+site:reuters.com+oil+OR+opec+OR+crude"),

    # --- Sentralbankar og makro ---
    ("Bank of England", "https://www.bankofengland.co.uk/rss/news"),
    ("Bank of Japan", "https://www.boj.or.jp/en/rss/whatsnew.xml"),
    ("IMF News", "https://www.imf.org/en/News/RSS?language=eng"),
    ("Treasury Dept", "https://home.treasury.gov/news/press-releases/feed"),

    # --- Tech / Nasdaq-drivarar ---
    ("Tom's Hardware", "https://www.tomshardware.com/feeds/all"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Register", "https://www.theregister.com/headlines.atom"),
    ("Hacker News", "https://hnrss.org/frontpage?points=150"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),

    # --- Google News tema-søk (desse døyr aldri) ---
    ("GN Fed-rente", GN % "when:6h+%22Federal+Reserve%22+interest+rate+decision"),
    ("GN CPI", GN % "when:12h+CPI+inflation+report+data"),
    ("GN Jobbtal", GN % "when:12h+nonfarm+payrolls+jobs+report"),
    ("GN OPEC-kutt", GN % "when:12h+OPEC+production+cut+OR+quota"),
    ("GN Oljelager", GN % "when:12h+crude+oil+inventories+EIA"),
    ("GN Hormuz", GN % "when:24h+Strait+of+Hormuz+OR+Red+Sea+shipping"),
    ("GN Russland-olje", GN % "when:12h+Russia+oil+sanctions+OR+exports"),
    ("GN Halvleiar-eksport", GN % "when:12h+semiconductor+export+controls+China"),
    ("GN Nvidia", GN % "when:12h+Nvidia+earnings+OR+guidance+OR+chips"),
    ("GN Renter", GN % "when:6h+Treasury+yields+bond+market"),
    ("GN Kina-økonomi", GN % "when:12h+China+economy+stimulus+OR+GDP"),
    ("GN Storm/orkan", GN % "when:24h+hurricane+Gulf+of+Mexico+oil+production"),
    ("GN Raffineri", GN % "when:24h+refinery+outage+OR+fire+OR+shutdown"),
    ("GN Sentralbank", GN % "when:12h+central+bank+rate+ECB+OR+BOJ+OR+BOE"),
]


def sjekk(par):
    namn, url = par
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return (namn, url, False, "HTTP %d" % resp.status_code)
        parsed = feedparser.parse(resp.content)
        n = len(parsed.entries)
        if n == 0:
            return (namn, url, False, "0 saker")
        tittel = parsed.entries[0].get("title", "")[:58]
        return (namn, url, True, "%3d saker | %s" % (n, tittel))
    except Exception as exc:
        return (namn, url, False, type(exc).__name__)


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        resultat = list(pool.map(sjekk, KANDIDATAR))

    ok = [r for r in resultat if r[2]]
    feil = [r for r in resultat if not r[2]]

    print("=== VERKAR (%d) ===" % len(ok))
    for namn, url, _, info in ok:
        print("  %-24s %s" % (namn, info))

    print("\n=== FEILA (%d) ===" % len(feil))
    for namn, url, _, info in feil:
        print("  %-24s %s" % (namn, info))

    print("\n--- YAML for dei som verkar ---")
    for namn, url, _, _ in ok:
        print("  - name: %s\n    url: %s" % (namn, url))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
