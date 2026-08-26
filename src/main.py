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
from .sources import news, prices, history
from . import rules, analyze, notify, technicals


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

    target = local_time.hour * 60 + local_time.minute
    wanted = config.get("briefing_hour", 8) * 60 + config.get("briefing_minute", 40)
    if abs(target - wanted) > config.get("briefing_window_minutes", 25):
        return False
    return state.briefing_due(local_time.strftime("%Y-%m-%d"))


def build_briefing(verdict, price_summary, world_summary, local_time):
    """Meldinga du får kvar morgon, 20 minutt før Oslo opnar."""
    direction = verdict.get("direction", "uklart")
    heading = {
        "opp": "OPP",
        "ned": "NED",
    }.get(direction, "UKLART - ingen retning å stole på")

    text = verdict.get("message") or verdict.get("reasoning", "")

    # Ikkje skriv "om 20 minutt" når det er 40. launchd køyrer kvart 20.
    # minutt og treffer ikkje klokkeslettet, så vi reknar det ut.
    minutter = (9 * 60) - (local_time.hour * 60 + local_time.minute)
    naar = ("om %d min" % minutter) if 0 < minutter <= 90 else "snart"

    return (
        "God morgon. Oslo opnar %s.\n"
        "RETNING: %s (%d %% sikker)\n\n"
        "%s\n\n"
        "Nasdaq og olje no: %s\n\n"
        "%s\n\n"
        "Dette er ei skildring av marknaden, ikkje eit råd. Avgjerda er di.\n"
        "%s"
    ) % (
        naar,
        heading,
        int(round(verdict.get("confidence", 0) * 100)),
        text,
        price_summary or "ingen prisdata",
        world_summary or "",
        local_time.strftime("%d.%m %H:%M"),
    )


def build_message(verdict, price_summary, local_time):
    text = verdict.get("message") or verdict.get("reasoning", "")
    label = {
        "nasdaq": "NASDAQ", "oil": "OLJE",
        "begge": "NASDAQ+OLJE", "ingen": "MARKNAD",
    }.get(verdict.get("asset"), "MARKNAD")
    arrow = {"opp": "OPP", "ned": "NED"}.get(verdict.get("direction"), "?")

    return "[%s %s | %s | %d%%] %s\n%s\n%s" % (
        label,
        arrow,
        verdict.get("horizon", ""),
        int(round(verdict.get("confidence", 0) * 100)),
        text,
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
        "%s\n"
        "%s" % (runs, items, alerts, kjelder, price_summary)
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

    message = (
        "STOR RØRSLE - RETNINGA ER UKLAR\n\n"
        "Det er %.1f %% utslag i marknaden og saka er dekt av %d kjelder, "
        "men signala peikar ulike vegar.\n\n"
        "%s\n\n"
        "%s\n\n"
        "Du får denne fordi det skjer noko stort, ikkje fordi det finst eit "
        "svar. Dette er ei skildring, ikkje eit råd.\n%s"
    ) % (move, coverage, verdict.get("reasoning", ""), price_summary,
         local_time.strftime("%d.%m %H:%M"))

    if dry_run:
        print("[main] DRY RUN - ville sendt uvisse-varsel:\n%s" % message)
        return
    if notify.send(message):
        state.record_uncertainty(local_time.strftime("%Y-%m-%d"))
        print("[main] uvisse-varsel sendt (%.1f %% utslag, %d kjelder)" % (move, coverage))


def _send_briefing(state, config, local_time, candidates, price_summary,
                   world_summary, technical_summary, api_key, dry_run):
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
        system_prompt=analyze.BRIEFING_PROMPT,
    )
    if verdict is None:
        print("[main] morgonmelding: vurderinga feila - inga melding")
        return
    if verdict.get("suspicious_content"):
        print("[main] morgonmelding: mistenkeleg innhald i materialet - inga melding")
        return

    message = build_briefing(verdict, price_summary, world_summary, local_time)
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
    tech_edge = None
    reports = []
    for key, spec in config.get("history_assets", {}).items():
        bars = history.fetch_daily(spec.get("symbol", key), spec.get("assetclass", "etf"))
        report = technicals.analyse(bars, spec.get("label", key))
        if report:
            reports.append(report)
    if reports:
        technical_summary = "\n".join(technicals.format_report(r) for r in reports)
        tech_edge = technicals.strongest_edge(reports)
        print("[main] chart: %d instrument | statistisk kant: %s" % (
            len(reports), tech_edge[2] if tech_edge else "ingen over støygrensa"))

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

    # 3b. Morgonmeldinga. Eigen veg gjennom systemet: ho går utanom
    # terskelen, cooldown og dagsgrensa, fordi ho ikkje er eit varsel.
    # Ho er den faste meldinga du har bede om, og "uklart" er eit gyldig
    # svar som skal sendast.
    if mode == "briefing" or briefing_due(local_time, config, state):
        _send_briefing(state, config, local_time, candidates, price_summary,
                       world_summary, technical_summary, api_key, dry_run)

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

    verdict = analyze.evaluate(candidates, price_summary, context_note, api_key,
                               world_summary=world_summary,
                               technical_summary=technical_summary)
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
