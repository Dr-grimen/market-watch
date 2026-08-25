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
from .sources import news, prices
from . import rules, analyze, notify


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
    # Helg: Nasdaq er stengd, olje-futures opnar søndag kveld.
    if local_time.weekday() == 5:            # laurdag
        return False
    if local_time.weekday() == 6 and local_time.hour < 22:  # søndag før opning
        return False
    # Natt i Noreg: du søv, og du får ingenting ut av eit varsel kl. 04.
    if 1 <= local_time.hour < 7:
        return False
    return True


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
    text = (
        "market-watch lever.\n"
        "Siste veka: %d køyringar, %d saker lesne, %d varsel sendt.\n"
        "%s" % (runs, items, alerts, price_summary)
    )
    if dry_run:
        print("[main] DRY RUN - ville sendt livsteikn:\n%s" % text)
    else:
        notify.send(text)
        print("[main] livsteikn sendt")


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

    # 2. Nyheiter (gratis)
    items = news.fetch_all(config)
    print("[main] henta %d saker" % len(items))

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

    api_key = env("ANTHROPIC_API_KEY")
    if not api_key:
        print("[main] ANTHROPIC_API_KEY manglar - kan ikkje vurdere")
        state.save()
        return 1

    verdict = analyze.evaluate(candidates, price_summary, context_note, api_key,
                               world_summary=world_summary)
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
    parser.add_argument("--mode", choices=["auto", "normal", "preopen"], default="auto",
                        help="auto les modus ut av klokka (standard)")
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
