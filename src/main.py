"""Éin køyring av market-watch.

Kjør lokalt:      python3 -m src.main
Tørrkøyring:      python3 -m src.main --dry-run
Før børsopning:   python3 -m src.main --mode preopen
"""

import argparse
import sys
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

from .config import load_config, env
from .state import State
from .sources import news, prices, history, calendar as market_calendar
from . import rules, analyze, notify, technicals, calibration, ensemble


def now_local(tzname):
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(tzname))


def resolve_mode(local_time, requested):
    """Avgjer om dette er ei før-opning-køyring.

    Vi les det ut av lokal tid, ikkje av cron-strengen: GitHub Actions
    køyrer alltid i UTC, og Noreg flyttar seg ein time to gonger i året.
    Amerikansk børs opnar 15:30 norsk tid, så vindauget 14:00-15:29 er
    der spørsmålet 'opnar det opp eller ned?' faktisk gir meining.
    """
    if requested != "auto":
        return requested
    if local_time.weekday() < 5 and 14 <= local_time.hour < 16:
        if local_time.hour == 15 and local_time.minute >= 30:
            return "normal"
        return "preopen"
    return "normal"


def should_run(local_time, mode):
    """Ikkje bruk pengar på tidspunkt der ingenting skjer."""
    if mode == "briefing":
        return local_time.weekday() < 5
    # Helg: Nasdaq er stengd, olje-futures opnar søndag kveld.
    if local_time.weekday() == 5:            # laurdag
        return False
    if local_time.weekday() == 6 and local_time.hour < 22:  # søndag før opning
        return False
    # Natt i Noreg: du søv, og du får ingenting ut av eit varsel kl. 04.
    if 1 <= local_time.hour < 7:
        return False
    return True


def briefing_due(local_time, config, state):
    """Er dette køyringa som skal sende morgonmeldinga?

    launchd køyrer kvart 20. minutt og treffer aldri 08:40 på minuttet,
    så vi opnar eit vindauge rundt klokkeslettet i staden. Sperra i
    state sørgjer for at det berre blir éi melding sjølv om to
    køyringar landar innanfor same vindauge.
    """
    if not config.get("briefing_enabled", True):
        return False
    if local_time.weekday() >= 5:
        return False

    now = local_time.hour * 60 + local_time.minute
    wanted = config.get("briefing_hour", 8) * 60 + config.get("briefing_minute", 40)
    if now < wanted - config.get("briefing_window_minutes", 25):
        return False

    # Etterslep. Macen søv med loket att, og då køyrer ingenting -
    # verken klokka 08:40 eller nokon annan gong. Fyrste køyring etter
    # at han vaknar skal difor sende meldinga likevel, så lenge dagen
    # framleis har noko igjen. Ei melding klokka 11 er langt betre enn
    # ingen melding, så lenge ho seier ærleg at ho er sein.
    if now > config.get("briefing_latest_hour", 15) * 60:
        return False
    return state.briefing_due(local_time.strftime("%Y-%m-%d"))


def build_briefing(verdict, price_summary, chart_summary, local_time, threshold,
                   pending=None):
    """Kort. Sondre bad om "ein rask og lett melding", og fekk det.

    Prosenten står likevel med. Ei melding som seier "sikker" utan tal
    er ikkje lett - ho er misvisande, og skilnaden mellom 66 % og 90 %
    er heile skilnaden.
    """
    direction = verdict.get("direction", "uklart")
    conf = float(verdict.get("confidence", 0.0))
    grunn = (verdict.get("message") or verdict.get("reasoning", "")).strip()
    # Éi setning er nok her. Resten ligg i loggen.
    fyrste = grunn.split(". ")[0]
    if fyrste and not fyrste.endswith("."):
        fyrste += "."

    # Usikker dag: berre den eine linja. Prosenten er utelaten med vilje -
    # på ein grå dag endrar det ingenting om det står 31 eller 44 %, og
    # Sondre bad om kort. På ein SIKKER dag står talet, for der er
    # skilnaden mellom 66 og 90 heile skilnaden.
    if direction not in ("opp", "ned") or conf < threshold:
        # Ein grå dag er greitt, men han er ikkje det same som ein tom
        # dag. Ligg det eit CPI- eller PCE-tal ute klokka 14:30, er
        # dagen grå NO og kan bli noko heilt anna om fem timar. Det er
        # verdt éi linje - då veit han når det er verdt å følgje med.
        varsel = ""
        if pending:
            fyrst = pending[0]
            varsel = "\n\n(%s kl. %s - kan bli noko seinare i dag.)" % (
                fyrst["name"], fyrst["time_local"])
        return "Halla Sjef 👋\nGrå dag i dag!%s\n\n%s" % (
            varsel, local_time.strftime("%d.%m %H:%M"))

    return "Halla Sjef 👋\nEg er sikker på %s i dag (%d %%).\n\n%s\n\n%s\n%s" % (
        direction.upper(), round(conf * 100), fyrste,
        price_summary or "", local_time.strftime("%d.%m %H:%M"))


def build_message(verdict, price_summary, local_time):
    """Varselet gjennom dagen. Same korte form som morgonmeldinga."""
    direction = verdict.get("direction", "uklart")
    grunn = (verdict.get("message") or verdict.get("reasoning", "")).strip()
    fyrste = grunn.split(". ")[0]
    if fyrste and not fyrste.endswith("."):
        fyrste += "."

    return "Halla Sjef 👋\nEg er sikker på %s (%d %%).\n\n%s\n\n%s\n%s" % (
        {"opp": "OPP", "ned": "NED"}.get(direction, "?"),
        round(float(verdict.get("confidence", 0)) * 100),
        fyrste,
        price_summary,
        local_time.strftime("%d.%m %H:%M"),
    )


def _handle_failure(state, config, reason, dry_run):
    """Varsle éin gong når verktøyet har vore nede ei stund.

    Dette er den einaste meldinga som ikkje handlar om marknaden. Utan
    henne ville eit knekt verktøy vore umogleg å skilje frå ein roleg dag.
    """
    threshold = config.get("failure_alert_after", 5)
    print("[main] FEIL: %s (strekk: %d)" % (reason, state.fail_streak + 1))
    if state.record_failure(threshold) and not dry_run:
        notify.send(
            "market-watch klarar ikkje å køyre: %s.\n"
            "Dette har skjedd %d gonger på rad. Du får ingen marknadsvarsel "
            "før dette er retta." % (reason, state.fail_streak)
        )


def _handle_recovery(state, dry_run):
    if state.record_success() and not dry_run:
        notify.send("market-watch er oppe att og overvakar som normalt.")


def _maybe_heartbeat(state, config, local_time, price_summary, dry_run):
    """Eit livsteikn i veka.

    Ikkje eit marknadssignal - berre eit prov på at verktøyet framleis
    køyrer, slik at stille kan tolkast som 'ingenting skjer' og ikkje
    som 'dette har vore dødt i tre veker'.
    """
    if not config.get("heartbeat_enabled", True):
        return
    if local_time.weekday() != config.get("heartbeat_weekday", 4):
        return
    if local_time.hour != config.get("heartbeat_hour", 17):
        return
    if not state.heartbeat_due():
        return

    runs, items, alerts = state.record_heartbeat()
    names = [f.get("name", "") for f in config.get("feeds", [])]
    dead = state.dead_feeds(names)
    kjelder = (
        "Alle %d kjelder leverer." % len(names) if not dead
        else "Desse har vore tomme i ei veke og bør sjekkast: %s"
             % ", ".join(dead[:8])
    )
    text = (
        "market-watch lever.\n"
        "Siste veka: %d køyringar, %d saker lesne, %d varsel sendt.\n"
        "%s\n\n"
        "%s\n\n"
        "%s" % (runs, items, alerts, kjelder, calibration.report(), price_summary)
    )
    if dry_run:
        print("[main] DRY RUN - ville sendt livsteikn:\n%s" % text)
    else:
        notify.send(text)
        print("[main] livsteikn sendt")


def _maybe_uncertainty_alert(state, config, local_time, verdict, candidates,
                             all_quotes, price_summary, dry_run):
    """Varsel om at det er STORT og at ingen veit kva veg.

    Portane her er med vilje strengare enn dei for eit vanleg varsel.
    Ei melding om uvisse er lett å sende for ofte, og gjer ho det, blir
    ho like verdilaus som eit varsel du ikkje kan stole på. Alle fire
    vilkåra må vere oppfylte, og du får maks eitt slikt i døgnet.
    """
    if not config.get("uncertainty_alert_enabled", True):
        return
    if local_time.hour < 7 or local_time.hour >= 23:
        return
    if not state.uncertainty_due(local_time.strftime("%Y-%m-%d")):
        return

    conf = float(verdict.get("confidence", 0.0))
    if conf > config.get("uncertainty_max_confidence", 0.4):
        return  # Lunken tvil er ikkje dramatisk uvisse.

    move = rules.max_abs_move(all_quotes)
    trigger = (config.get("price_move_threshold_pct", 0.8)
               * config.get("uncertainty_move_multiplier", 1.8))
    if move < trigger:
        return  # Ingenting rører seg. Då er uvissa berre ein roleg dag.

    coverage = rules.heaviest_coverage(candidates)
    if coverage < config.get("uncertainty_min_sources", 4):
        return  # Store ting blir dekte av mange. Er dei ikkje det, er det ikkje stort.

    grunn = (verdict.get("reasoning") or "").strip().split(". ")[0]
    if grunn and not grunn.endswith("."):
        grunn += "."

    message = (
        "Halla Sjef 👋\n"
        "Noko stort skjer - men eg veit ikkje kva veg.\n\n"
        "%.1f %% utslag, %d kjelder skriv om det, og signala sprikar.\n"
        "%s\n\n"
        "%s\n%s"
    ) % (move, coverage, grunn, price_summary,
         local_time.strftime("%d.%m %H:%M"))

    if dry_run:
        print("[main] DRY RUN - ville sendt uvisse-varsel:\n%s" % message)
        return
    if notify.send(message):
        state.record_uncertainty(local_time.strftime("%Y-%m-%d"))
        print("[main] uvisse-varsel sendt (%.1f %% utslag, %d kjelder)" % (move, coverage))


# Kva historikk-instrumentet svarar til blant dei live prisane. QQQ
# følgjer Nasdaq, USO og BNO følgjer olja.
_LIVE_MAP = {"nasdaq": "nasdaq"}


def _live_move(quotes_by_asset, history_key):
    """Rørsla no i det aktivumet historikken gjeld.

    Vi tek den største rørsla i gruppa: futures og spot spriker litt, og
    det er det kraftigaste utslaget som seier noko om opninga.
    """
    quotes = quotes_by_asset.get(_LIVE_MAP.get(history_key, "")) or []
    if not quotes:
        return None
    return max((q.get("change_pct", 0.0) for q in quotes), key=abs)


def _maybe_event_alert(state, config, local_time, pending_before, kalender,
                       price_summary, dry_run):
    """Talet kom. Dette er RAPPORT, ikkje spådom.

    Om morgonen står det at Core PCE kjem klokka 14:30. Klokka 14:32
    finst det eit faktisk tal, og då er den viktigaste opplysninga i
    heile døgnet tilgjengeleg - ikkje som ei vurdering, men som eit
    faktum. Sondre skal ha det med ein gong, og han skal ha det utan
    at nokon har gjetta på kva det tyder.
    """
    if not config.get("event_alert_enabled", True):
        return
    today = local_time.strftime("%Y-%m-%d")

    for event in (kalender.get("economic") or []):
        if not event["actual"]:
            continue
        if market_calendar._priority(event["name"]) != 0:
            continue          # berre dei tyngste tala
        if state.event_reported(today, event["name"]):
            continue

        avvik = ""
        if event["consensus"]:
            avvik = " - venta var %s" % event["consensus"]
        message = "Halla Sjef 👋\n%s kom inn på %s%s.\n\n%s\n%s" % (
            event["name"], event["actual"], avvik,
            price_summary, local_time.strftime("%d.%m %H:%M"))

        if dry_run:
            print("[main] DRY RUN - ville sendt tal-melding:\n%s" % message)
            state.record_event(today, event["name"])
            continue
        if notify.send(message):
            state.record_event(today, event["name"])
            print("[main] tal-melding sendt: %s = %s" % (event["name"], event["actual"]))


def _maybe_move_alert(state, config, local_time, all_quotes, dry_run):
    """Det rører seg NO. Også rein rapport.

    Ingen påstand om kva som skjer vidare - berre at Nasdaq har flytta
    seg meir enn ein vanleg dag, og kva veg. Éi melding per nivå, så
    ein dag som fell jamt ikkje gir tjue meldingar.
    """
    if not config.get("move_alert_enabled", True):
        return
    if local_time.hour < 7 or local_time.hour >= 23:
        return

    steg = config.get("move_alert_levels", [1.0, 2.0, 3.0])
    move = rules.max_abs_move(all_quotes)
    today = local_time.strftime("%Y-%m-%d")
    alt_meldt = state.move_mark(today)

    naadd = [s for s in steg if move >= s and s > alt_meldt]
    if not naadd:
        return
    niva = max(naadd)

    retning = "opp"
    for quote in all_quotes:
        if abs(quote.get("change_pct", 0.0)) == move:
            retning = "opp" if quote.get("change_pct", 0) > 0 else "ned"
            break

    message = "Halla Sjef 👋\nDet rører seg - Nasdaq %s %.1f %% no.\n\n%s\n%s" % (
        retning, move, price_summary_of(all_quotes), local_time.strftime("%d.%m %H:%M"))

    if dry_run:
        print("[main] DRY RUN - ville sendt rørsle-melding (nivå %.1f):\n%s"
              % (niva, message))
        state.record_move(today, niva)
        return
    if notify.send(message):
        state.record_move(today, niva)
        print("[main] rørsle-melding sendt (%s %.1f %%)" % (retning, move))


def price_summary_of(quotes):
    return prices.summarize(quotes)


def _maybe_lean_alert(state, config, local_time, verdict, price_summary,
                      base_rate, dry_run):
    """Melding når det lener, men ikkje er sikkert.

    Faren med denne er at ho blir lesen som eit varsel. Difor står
    confidence i overskrifta, og basisraten rett under: er hellinga
    58 % når 56 % av alle dagar går opp uansett, har du fått vite at
    du har to prosentpoeng - ikkje at du har eit signal.
    """
    if not config.get("lean_alert_enabled", True):
        return
    direction = verdict.get("direction")
    if direction not in ("opp", "ned"):
        return

    conf = float(verdict.get("confidence", 0.0))
    if conf < config.get("lean_threshold", 0.55):
        return
    if local_time.hour < 7 or local_time.hour >= 23:
        return
    if state.leans_today() >= config.get("max_lean_alerts_per_day", 3):
        return
    if state.in_lean_cooldown(direction, config.get("lean_cooldown_minutes", 240)):
        return

    grunn = (verdict.get("message") or verdict.get("reasoning", "")).strip()
    fyrste = grunn.split(". ")[0]
    if fyrste and not fyrste.endswith("."):
        fyrste += "."

    # "Teikn til" og ikkje "sikker på". Same melding med sterkare ord
    # ville vore ei lita løgn kvar gong, og etter tjue slike ville han
    # ikkje visst kva orda betydde lenger.
    message = "Halla Sjef 👋\nEg ser teikn til %s (%d %%).\n\n%s\n\n%s\n%s" % (
        direction.upper(), round(conf * 100), fyrste,
        price_summary, local_time.strftime("%d.%m %H:%M"))

    if dry_run:
        print("[main] DRY RUN - ville sendt lean-varsel:\n%s" % message)
        return
    if notify.send(message):
        state.record_lean(direction)
        print("[main] lean-varsel sendt (%s, %.0f %%)" % (direction, conf * 100))


def _send_briefing(state, config, local_time, candidates, price_summary,
                   world_summary, technical_summary, calendar_summary,
                   chart_summary, ensemble_summary, quotes_by_asset,
                   pending, api_key, dry_run):
    """Sender morgonmeldinga. Feilar ho, blir det stille - ikkje eit krasj."""
    today = local_time.strftime("%Y-%m-%d")
    if not api_key:
        print("[main] morgonmelding: manglar API-nøkkel - hoppar over")
        return

    verdict = analyze.evaluate(
        candidates, price_summary,
        context_note=("Oslo Børs opnar om 20 minutt. Den amerikanske børsen "
                      "opnar 15:30 norsk tid. Oppsummer kva som ligg føre no."),
        api_key=api_key,
        world_summary=world_summary,
        technical_summary=technical_summary,
        calendar_summary=calendar_summary,
        ensemble_summary=ensemble_summary,
        system_prompt=analyze.BRIEFING_PROMPT,
    )
    if verdict is None:
        print("[main] morgonmelding: vurderinga feila - inga melding")
        return
    if verdict.get("suspicious_content"):
        print("[main] morgonmelding: mistenkeleg innhald i materialet - inga melding")
        return

    nasdaq_no = None
    for q in (quotes_by_asset.get("nasdaq") or []):
        nasdaq_no = q.get("price")
        break
    calibration.record(today, verdict.get("direction"),
                       verdict.get("confidence", 0.0), nasdaq_no, "briefing")

    message = build_briefing(verdict, price_summary, chart_summary, local_time,
                             config.get("confidence_threshold", 0.75), pending)
    if dry_run:
        print("[main] DRY RUN - ville sendt morgonmelding:\n%s" % message)
        return
    if notify.send(message):
        state.record_briefing(today)
        print("[main] morgonmelding sendt (%s, %.0f %%)" % (
            verdict.get("direction"), verdict.get("confidence", 0) * 100))
    else:
        print("[main] morgonmelding: sending feila")


def run(mode="auto", dry_run=False):
    config = load_config()
    tzname = config.get("timezone", "Europe/Oslo")
    local_time = now_local(tzname)
    mode = resolve_mode(local_time, mode)

    if not should_run(local_time, mode):
        print("[main] utanfor aktiv tid (%s) - hoppar over" % local_time.strftime("%a %H:%M"))
        return 0

    print("[main] %s | modus: %s" % (local_time.strftime("%a %d.%m %H:%M"), mode))

    state = State.load()

    if state.alerts_today() >= config.get("max_alerts_per_day", 6):
        print("[main] dagleg varselgrense nådd - stille resten av døgnet")
        state.save()
        return 0

    # 1. Prisar (gratis)
    quotes_by_asset = prices.fetch_all(config.get("assets", {}))
    all_quotes = []
    for quotes in quotes_by_asset.values():
        all_quotes.extend(quotes)
    price_summary = prices.summarize(all_quotes)
    print("[main] prisar: %s" % (price_summary or "ingen data"))

    # Verdsbiletet. Eige kall, og halde strengt utanfor all_quotes:
    # desse skal aldri kunne utløyse eit varsel på eiga hand.
    context_config = config.get("context_assets", {})
    world_quotes = prices.fetch_all(context_config) if context_config else {}
    world_summary = prices.summarize_grouped(world_quotes, context_config)
    world_flat = [q for group in world_quotes.values() for q in group]
    if world_flat:
        movers = prices.biggest_movers(world_flat)
        print("[main] verda: %d tal, størst rørsle: %s" % (
            len(world_flat), prices.summarize(movers) or "alt roleg"))

    # Chart og statistikk (gratis - historikken ligg i cache på disk)
    technical_summary = ""
    chart_summary = ""
    tech_edge = None
    reports = []
    for key, spec in config.get("history_assets", {}).items():
        bars = history.fetch_daily(spec.get("symbol", key), spec.get("assetclass", "etf"))
        report = technicals.analyse(bars, spec.get("label", key))
        if report:
            reports.append(report)
    if reports:
        technical_summary = "\n".join(technicals.format_report(r) for r in reports)
        chart_summary = technicals.short_summary(reports[0])

        # BNF-oppsettet. Slår sjeldan ut - nokre gonger i året - men det
        # er det einaste vi har målt der forteiknet har vore konsistent.
        bnf = technicals.bnf_setup(history.fetch_daily("QQQ"))
        if bnf:
            technical_summary += "\n\n" + technicals.format_bnf(bnf, "QQQ")
            print("[main] BNF-oppsett aktivt: %.1f %% under snitt, RSI %.0f"
                  % (bnf["avvik"], bnf["rsi"]))
        tech_edge = technicals.strongest_edge(reports)

        # Kva rørsla i natt faktisk tyder. Dette er det næraste vi kjem
        # eit ærleg svar på "opnar det opp?" - og på kvifor det spørsmålet
        # ikkje er det same som "endar dagen opp?".
        gap_lines = []
        for key, spec in config.get("history_assets", {}).items():
            bars = history.fetch_daily(spec.get("symbol", key),
                                       spec.get("assetclass", "etf"))
            stats = technicals.gap_statistics(bars)
            live = _live_move(quotes_by_asset, key)
            text = technicals.gap_context(stats, live, spec.get("label", key))
            if text:
                gap_lines.append(text)
        if gap_lines:
            technical_summary += ("\n\nRØRSLE OVER NATTA - KVA HO FAKTISK SEIER:\n"
                                  + "\n".join(gap_lines))
        print("[main] chart: %d instrument | statistisk kant: %s" % (
            len(reports), tech_edge[2] if tech_edge else "ingen over støygrensa"))

    # Kalenderen (gratis). Det einaste i heile verktøyet som er fakta
    # og ikkje tolking: kva som er planlagt, og om det har kome enno.
    calendar_summary = ""
    ventar, pending, kalender = 0, [], {}
    try:
        kalender = market_calendar.fetch_today(
            local_time.strftime("%Y-%m-%d"), tzname)
        calendar_summary = market_calendar.format_calendar(kalender)
        ventar, pending = market_calendar.pending_count(kalender)
        print("[main] kalender: %d store tal ventar enno i dag" % ventar)
    except Exception as exc:
        print("[main] kalenderen svarte ikkje (%s) - held fram utan"
              % type(exc).__name__)

    # Signalsamlinga: fleire uavhengige signal, kvart med si MÅLTE
    # treffrate. Peikar dei ulike vegar, er usikkert det rette svaret.
    ensemble_summary = ""
    base_rate = None
    if reports:
        base_rate = reports[0]["base_rates"].get(1)
        try:
            qqq = history.fetch_daily("QQQ")
            kryss = dict((k, ensemble._aligned(qqq, v))
                         for k, v in ensemble.load_cross().items())
            res = ensemble.evaluate(qqq, kryss)
            ensemble_summary = ensemble.format_report(res, qqq)
            if res:
                print("[main] signal: %d slo ut, %d med målt kant -> %s" % (
                    len(res["votes"]), len(res["weighted"]), res["direction"]))
        except Exception as exc:
            print("[main] signalsamlinga feila (%s) - held fram utan"
                  % type(exc).__name__)

    # Døm gårsdagens vurderingar mot det som faktisk hende. Utan dette
    # er eit confidence-tal berre ein påstand modellen skriv om seg sjølv.
    if reports:
        avgjort = calibration.settle(history.fetch_daily(
            config.get("history_assets", {}).get("nasdaq", {}).get("symbol", "QQQ")))
        if avgjort:
            print("[main] kalibrering: dømde %d gamle vurderingar" % avgjort)

    # 2. Nyheiter (gratis)
    items = news.fetch_all(config)
    print("[main] henta %d saker" % len(items))

    # Kva kjelder leverte? Ein feed som stille døyr er usynleg utan dette.
    delivered = set(item.get("source", "") for item in items)
    for feed in config.get("feeds", []):
        state.record_feed_result(feed.get("name", ""), feed.get("name") in delivered)

    # Helsesjekk: får vi korkje prisar eller nyheiter, er noko gale
    # med sjølve verktøyet - ikkje med marknaden.
    if not all_quotes and not items:
        _handle_failure(state, config, "korkje pris- eller nyheitsdata kom inn", dry_run)
        state.save()
        return 1

    state.record_run(len(items))
    _handle_recovery(state, dry_run)
    _maybe_heartbeat(state, config, local_time, price_summary, dry_run)

    # 3. Regelfilter (gratis) - her forsvinn det meste
    candidates = rules.prefilter(items, config, state)
    big_move = rules.price_alarm(all_quotes, config.get("price_move_threshold_pct", 0.8))
    print("[main] %d kandidatar etter filter (stor prisrørsle: %s)" % (len(candidates), big_move))

    api_key = env("ANTHROPIC_API_KEY")

    # 3a. Dei to faktameldingane. Desse treng ingen vurdering og ingen
    # API-nøkkel: eit tal som er sleppt, og ei rørsle som skjer, er
    # ikkje spådommar. Difor går dei ut med ein gong.
    if kalender:
        _maybe_event_alert(state, config, local_time, pending, kalender,
                           price_summary, dry_run)
    _maybe_move_alert(state, config, local_time, all_quotes, dry_run)

    # 3b. Morgonmeldinga. Eigen veg gjennom systemet: ho går utanom
    # terskelen, cooldown og dagsgrensa, fordi ho ikkje er eit varsel.
    # Ho er den faste meldinga du har bede om, og "uklart" er eit gyldig
    # svar som skal sendast.
    if mode == "briefing" or briefing_due(local_time, config, state):
        _send_briefing(state, config, local_time, candidates, price_summary,
                       world_summary, technical_summary, calendar_summary,
                       chart_summary, ensemble_summary, quotes_by_asset,
                       pending, api_key, dry_run)

    if not candidates and not big_move:
        print("[main] ingenting å vurdere - stille")
        state.save()
        return 0

    if not candidates:
        print("[main] prisrørsle utan nyheitsdekning - for tynt grunnlag, stille")
        state.save()
        return 0

    # 4. Claude Haiku (kostar pengar - berre på det som overlevde)
    context_note = ""
    if mode == "preopen":
        context_note = (
            "Dette er ei vurdering FØR den amerikanske børsen opnar. "
            "Spørsmålet brukaren vil ha svar på er: tyder noko på at marknaden "
            "opnar opp eller ned? Bruk horisont 'ved opning' dersom det passar."
        )
    if big_move:
        context_note += " Det er allereie ei stor prisrørsle i gang."

    if not api_key:
        print("[main] ANTHROPIC_API_KEY manglar - kan ikkje vurdere")
        state.save()
        return 1

    if tech_edge:
        context_note += (
            " Teknisk statistikk med tyngde: %s. Dette er bakgrunn, ikkje "
            "eit varsel i seg sjølv." % tech_edge[2])

    try:
        verdict = analyze.evaluate(candidates, price_summary, context_note, api_key,
                                   world_summary=world_summary,
                                   technical_summary=technical_summary,
                                   calendar_summary=calendar_summary,
                                   ensemble_summary=ensemble_summary)
    except analyze.FatalKontoFeil as exc:
        # Dette går ikkje over av seg sjølv. Meldinga skal seie kva
        # Sondre må gjere, ikkje kva som teknisk gjekk gale - han sit
        # kanskje på ei strand og har ingen anna informasjon enn denne.
        _handle_failure(state, config, str(exc), dry_run)
        state.save()
        return 1
    if verdict is None:
        _handle_failure(state, config, "Claude-kallet feila", dry_run)
        state.save()
        return 1
    state.record_success()

    conf = float(verdict.get("confidence", 0.0))
    direction = verdict.get("direction", "uklart")
    asset = verdict.get("asset", "ingen")
    print("[main] vurdering: %s %s conf=%.2f - %s" % (
        asset, direction, conf, verdict.get("reasoning", "")))

    # 5. Portane. Alle må passerast før du får ein lyd frå telefonen.
    if verdict.get("suspicious_content"):
        print("[main] materialet inneheldt mistenkeleg tekst - stille")
        state.save()
        return 0

    if direction == "uklart" or asset == "ingen":
        # Vanleg tvil er stille. Det er sjølve prinsippet verktøyet står på.
        # Men det finst eitt unntak: når marknaden rører seg kraftig, heile
        # verda skriv om det, OG signala framleis sprikar - då er sjølve
        # uvissa nyheita, og stille ville vore misvisande.
        _maybe_uncertainty_alert(state, config, local_time, verdict, candidates,
                                 all_quotes, price_summary, dry_run)
        print("[main] uklar retning - stille (dette er meininga)")
        state.save()
        return 0

    threshold = config.get("confidence_threshold", 0.75)
    if conf < threshold:
        # Under terskelen for eit sikkert varsel - men lener det tydeleg
        # ein veg, skal han få vite det. Med talet på, og med basisraten
        # ved sida av, så han ser kor tynn hellinga eigentleg er.
        _maybe_lean_alert(state, config, local_time, verdict, price_summary,
                          base_rate, dry_run)
        print("[main] %.2f under terskel %.2f - stille" % (conf, threshold))
        state.save()
        return 0

    if state.in_cooldown(asset, direction, config.get("cooldown_minutes", 180)):
        print("[main] allereie varsla om %s/%s nyleg - stille" % (asset, direction))
        state.save()
        return 0

    # 6. Send
    message = build_message(verdict, price_summary, local_time)
    if dry_run:
        print("[main] DRY RUN - ville sendt:")
        print(message)
    else:
        if notify.send(message):
            state.record_alert(asset, direction)
            print("[main] varsel sendt")
        else:
            print("[main] varsling feila")

    state.save()
    return 0


def doctor():
    """Sjekkar oppsettet og seier rett ut kva som manglar."""
    config = load_config()
    problems = []

    print("market-watch - oppsettsjekk")
    print("-" * 46)

    channel = env("NOTIFIER", "telegram")
    print("Varslingskanal      : %s" % channel)
    if channel == "telegram":
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            status = "OK" if env(name) else "MANGLAR"
            print("  %-18s: %s" % (name, status))
            if not env(name):
                problems.append(name)
    elif channel == "twilio_sms":
        for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
                     "TWILIO_FROM_NUMBER", "ALERT_PHONE_NUMBER"):
            status = "OK" if env(name) else "MANGLAR"
            print("  %-18s: %s" % (name, status))
            if not env(name):
                problems.append(name)

    has_key = bool(env("ANTHROPIC_API_KEY"))
    print("ANTHROPIC_API_KEY   : %s" % ("OK" if has_key else "MANGLAR"))
    if not has_key:
        problems.append("ANTHROPIC_API_KEY")

    print("Kjelder             : %d feeds, %d Reddit-forum"
          % (len(config.get("feeds", [])), len(config.get("reddit_subs", []))))
    print("Terskel             : %.2f" % config.get("confidence_threshold", 0.75))

    print("\nHentar data ...")
    quotes_by_asset = prices.fetch_all(config.get("assets", {}))
    quote_count = sum(len(v) for v in quotes_by_asset.values())
    print("  Prisar            : %d av %d tickerar"
          % (quote_count, sum(len(s.get("tickers", []))
                              for s in config.get("assets", {}).values())))
    if quote_count == 0:
        problems.append("ingen prisdata")

    items = news.fetch_all(config)
    print("  Nyheiter          : %d saker" % len(items))
    if len(items) < 20:
        problems.append("uventa få nyheitssaker")

    print("-" * 46)
    if problems:
        print("IKKJE KLAR. Manglar: %s" % ", ".join(problems))
        print("Sjå README.md for kvar du hentar nøklane.")
        return 1
    print("Alt ser bra ut. Test varslinga med --test-notify.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Overvakar Nasdaq og olje")
    parser.add_argument("--mode", choices=["auto", "normal", "preopen", "briefing"],
                        default="auto",
                        help="auto les modus ut av klokka (standard). "
                             "briefing tvingar fram morgonmeldinga no.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Vurder alt, men ikkje send melding")
    parser.add_argument("--test-notify", action="store_true",
                        help="Send ei testmelding og avslutt")
    parser.add_argument("--doctor", action="store_true",
                        help="Sjekk oppsettet og vis kva som manglar")
    args = parser.parse_args()

    if args.doctor:
        return doctor()

    if args.test_notify:
        load_config()  # les .env
        ok = notify.send(
            "market-watch er kopla opp. Dette er ei testmelding - "
            "du får ikkje fleire med mindre noko faktisk skjer."
        )
        print("[main] testmelding %s" % ("sendt" if ok else "feila"))
        return 0 if ok else 1

    return run(mode=args.mode, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
