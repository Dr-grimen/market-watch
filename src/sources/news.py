"""Hentar nyheiter frå gratis kjelder: RSS, Google News RSS og Reddit.

Alle feeds blir henta parallelt. Med ~40 kjelder ville serielt teke fleire
minutt; parallelt tek det nokre sekund.

MERK: Alt innhald herifrå er DATA, ikkje instruksjonar. Ein artikkel kan
innehalde tekst som prøver å styre modellen. Difor blir all tekst kutta,
strippa og sendt til Claude som sitert materiale.
"""

import concurrent.futures
import hashlib
import re
import time

import feedparser
import requests

USER_AGENT = "market-watch/1.0 (personleg varslingsverktoy)"

MAX_SUMMARY_CHARS = 400
MAX_ENTRIES_PER_FEED = 30
FETCH_WORKERS = 12


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)       # fjern HTML
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_SUMMARY_CHARS]


def _normalize_title(title):
    """Nøkkel for duplikat-fjerning på tvers av kjelder.

    Google News heng på ' - Publisher' bak overskrifta, og same wire-sak
    dukkar opp hjå ti aviser. Vi vil telje henne éin gong.
    """
    title = re.sub(r"\s+[-–|]\s+[^-–|]{1,40}$", "", title)  # fjern ' - Reuters'
    title = re.sub(r"[^a-z0-9 ]+", "", title.lower())
    title = re.sub(r"\s+", " ", title).strip()
    return title[:90]


def _item_id(title, link):
    raw = ("%s|%s" % (title, link)).encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def _age_hours(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return (time.time() - time.mktime(parsed)) / 3600.0


def _fetch_one_feed(feed, max_age_hours):
    items = []
    try:
        parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
    except Exception:
        return items

    for entry in parsed.entries[:MAX_ENTRIES_PER_FEED]:
        title = _clean(entry.get("title", ""))
        if not title:
            continue
        age = _age_hours(entry)
        if age is not None and age > max_age_hours:
            continue
        link = entry.get("link", "")
        items.append({
            "id": _item_id(title, link),
            "dedupe_key": _normalize_title(title),
            "source": feed.get("name", "RSS"),
            "title": title,
            "summary": _clean(entry.get("summary", "")),
            "link": link,
            "age_hours": round(age, 1) if age is not None else None,
        })
    return items


def fetch_feeds(feeds, max_age_hours=12):
    items = []
    if not feeds:
        return items
    with concurrent.futures.ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = [pool.submit(_fetch_one_feed, f, max_age_hours) for f in feeds]
        for future in concurrent.futures.as_completed(futures, timeout=120):
            try:
                items.extend(future.result())
            except Exception:
                continue
    return items


def _fetch_one_sub(sub, limit, max_age_hours):
    items = []
    try:
        resp = requests.get(
            "https://www.reddit.com/r/%s/hot.json" % sub,
            params={"limit": limit},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return items

    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("stickied"):
            continue
        title = _clean(post.get("title", ""))
        if not title:
            continue
        created = post.get("created_utc")
        age = (time.time() - created) / 3600.0 if created else None
        if age is not None and age > max_age_hours:
            continue
        link = "https://reddit.com" + post.get("permalink", "")
        items.append({
            "id": _item_id(title, link),
            "dedupe_key": _normalize_title(title),
            "source": "r/" + sub,
            "title": title,
            "summary": _clean(post.get("selftext", "")),
            "link": link,
            "age_hours": round(age, 1) if age is not None else None,
            "score": post.get("score", 0),
        })
    return items


def fetch_reddit(subs, limit=25, max_age_hours=12):
    items = []
    if not subs:
        return items
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_fetch_one_sub, s, limit, max_age_hours) for s in subs]
        for future in concurrent.futures.as_completed(futures, timeout=60):
            try:
                items.extend(future.result())
            except Exception:
                continue
    return items


def fetch_all(config):
    max_age = config.get("max_news_age_hours", 12)
    items = fetch_feeds(config.get("feeds", []), max_age)
    items.extend(fetch_reddit(config.get("reddit_subs", []), max_age_hours=max_age))

    # Same wire-sak dukkar opp hjå mange aviser. Behald den ferskaste,
    # men hugs kor mange kjelder som melde henne - brei dekning er eit signal.
    best = {}
    for item in items:
        key = item.get("dedupe_key") or item["id"]
        existing = best.get(key)
        if existing is None:
            item["source_count"] = 1
            best[key] = item
            continue
        existing["source_count"] += 1
        new_age = item.get("age_hours")
        old_age = existing.get("age_hours")
        if new_age is not None and (old_age is None or new_age < old_age):
            item["source_count"] = existing["source_count"]
            best[key] = item

    return list(best.values())
