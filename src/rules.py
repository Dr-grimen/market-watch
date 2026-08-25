"""Gratis-filteret.

Dette laget kastar 97-98 % av nyheitsstraumen utan eit einaste API-kall.
Berre det som overlever hamnar hjå Claude - det er slik rekninga held seg låg.
"""

import re


def _text_of(item):
    return (item.get("title", "") + " " + item.get("summary", "")).lower()


def is_noise(item, noise_words):
    text = _text_of(item)
    for word in noise_words:
        if word.lower() in text:
            return True
    return False


def match_assets(item, keywords):
    """Returnerer liste med aktiva-nøklar saka rører ved."""
    text = _text_of(item)
    hits = []
    for asset, words in keywords.items():
        for word in words:
            if word.lower() in text:
                hits.append(asset)
                break
    return hits


def score(item, assets_hit):
    """Enkel prioritering, så vi sender dei mest lovande sakene til Claude først."""
    text = _text_of(item)
    points = len(assets_hit) * 2

    # Ferskt slår gammalt.
    age = item.get("age_hours")
    if age is not None:
        if age <= 2:
            points += 4
        elif age <= 6:
            points += 2

    # Hendingar som historisk flyttar marknaden.
    heavy = [
        "fed", "rate cut", "rate hike", "cpi", "inflation", "opec",
        "production cut", "sanctions", "strait of hormuz", "earnings",
        "guidance", "tariff", "jobs report", "nonfarm", "inventories",
    ]
    for word in heavy:
        if word in text:
            points += 3

    # Melder mange aviser same sak, er ho truleg reell og ikkje støy.
    points += min(item.get("source_count", 1) - 1, 4) * 2

    # Reddit-støy skal ikkje slå ekte nyheiter.
    if item.get("source", "").startswith("r/"):
        points -= 2
        if item.get("score", 0) > 2000:
            points += 2

    return points


STOPWORDS = set("""
a an the of in on for to and or as at by with from is are was were be been
says say said after before amid over under new latest report reports
""".split())


def _keywords_of(item):
    title = item.get("title", "")
    # Google News heng på ' - Bloomberg.com'. Utan å fjerne den halen
    # blir publisistnamnet talt som eit innhaldsord og øydelegg samanlikninga.
    title = re.sub(r"\s+[-–|]\s+[^-–|]{1,40}$", "", title)
    words = set()
    for word in title.lower().split():
        word = "".join(ch for ch in word if ch.isalnum())
        if len(word) > 2 and word not in STOPWORDS:
            words.add(word)
    return words


def _is_near_duplicate(words, kept, threshold=0.5):
    """Same hending, ulik overskrift.

    Ei sak som 'Fed's Collins says rates may need to rise' dukkar opp i fem
    ulike innpakningar. Utan dette går halve Claude-kallet til å lese
    same nyheit om att.
    """
    if not words:
        return None
    for other_words, other_item in kept:
        if not other_words:
            continue
        overlap = len(words & other_words) / float(min(len(words), len(other_words)))
        if overlap >= threshold:
            return other_item
    return None


def prefilter(items, config, state):
    """Nyheiter inn, kandidatar ut. Ingen kostnad."""
    keywords = config.get("keywords", {})
    noise_words = config.get("noise_words", [])
    candidates = []

    for item in items:
        if not state.is_new(item["id"]):
            continue
        state.mark_seen(item["id"])

        if is_noise(item, noise_words):
            continue

        assets_hit = match_assets(item, keywords)
        if not assets_hit:
            continue

        item = dict(item)
        item["assets"] = assets_hit
        item["rule_score"] = score(item, assets_hit)
        candidates.append(item)

    candidates.sort(key=lambda x: x["rule_score"], reverse=True)

    # Behald berre éin versjon av kvar hending, den høgast rangerte.
    # At fleire aviser melde henne blir talt opp i staden.
    limit = config.get("max_items_to_llm", 12)
    kept = []
    selected = []
    for item in candidates:
        words = _keywords_of(item)
        duplicate_of = _is_near_duplicate(words, kept)
        if duplicate_of is not None:
            duplicate_of["source_count"] = duplicate_of.get("source_count", 1) + 1
            continue
        kept.append((words, item))
        selected.append(item)
        if len(selected) >= limit:
            break

    return selected


def price_alarm(quotes, threshold_pct):
    """Sann dersom ei prisrørsle åleine er stor nok til å vere interessant."""
    for quote in quotes:
        if abs(quote.get("change_pct", 0.0)) >= threshold_pct:
            return True
    return False
