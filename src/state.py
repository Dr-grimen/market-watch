"""Hugsar kva vi har sett før, så du ikkje får same varselet to gonger.

Lagrar til state.json. På GitHub Actions blir fila teken vare på
mellom køyringar via cache-steget i workflowen.
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state.json"

# Kast bort sett-merke eldre enn dette, så fila ikkje veks i det uendelege.
SEEN_TTL_SECONDS = 60 * 60 * 72


class State(object):
    def __init__(self, data=None):
        data = data or {}
        self.seen = data.get("seen", {})            # item_id -> timestamp
        self.last_alert = data.get("last_alert", {})  # "asset:direction" -> timestamp
        self.alert_log = data.get("alert_log", [])    # liste med timestamps

        # Helsesporing. Utan dette ser eit knekt verktøy nøyaktig ut
        # som ein roleg marknad - begge deler er stille.
        self.fail_streak = data.get("fail_streak", 0)
        self.failure_notified = data.get("failure_notified", False)
        self.last_heartbeat = data.get("last_heartbeat", 0)
        self.week_runs = data.get("week_runs", 0)
        self.week_items = data.get("week_items", 0)
        self.week_alerts = data.get("week_alerts", 0)
        self.last_briefing_date = data.get("last_briefing_date", "")
        self.last_uncertainty_date = data.get("last_uncertainty_date", "")
        self.reported_events = data.get("reported_events", {})  # "dato|namn" -> tid
        self.move_marks = data.get("move_marks", {})            # dato -> største nivå meldt
        # Kva marknaden stod i da vi sist brukte pengar paa ei vurdering.
        # Utan dette kan vi ikkje vite om noko har endra seg sidan sist,
        # og daa maa vi enten spoerje Claude kvar gong (dyrt) eller
        # sjeldan (treigt). Med dette kan vi sjekke ofte og spoerje sjeldan.
        self.last_eval_price = data.get("last_eval_price")
        self.last_eval_time = data.get("last_eval_time", 0)
        self.lean_log = data.get("lean_log", [])          # tidspunkt
        self.last_lean = data.get("last_lean", {})        # retning -> tidspunkt

        # Kva kjelder som faktisk svarte sist. Ein feed som stille sluttar
        # å levere er den farlegaste feilen i heile verktøyet: alt ser ut
        # til å verke, men du overvakar mindre og mindre av verda.
        self.feed_health = data.get("feed_health", {})

    @classmethod
    def load(cls):
        if STATE_PATH.exists():
            try:
                with open(STATE_PATH, "r", encoding="utf-8") as fh:
                    return cls(json.load(fh))
            except (ValueError, OSError):
                pass
        return cls()

    def save(self):
        now = time.time()
        self.seen = dict(
            (k, v) for k, v in self.seen.items() if now - v < SEEN_TTL_SECONDS
        )
        self.alert_log = [t for t in self.alert_log if now - t < 60 * 60 * 24]
        self.lean_log = [t for t in self.lean_log if now - t < 60 * 60 * 24]
        payload = {
            "seen": self.seen,
            "last_alert": self.last_alert,
            "alert_log": self.alert_log,
            "fail_streak": self.fail_streak,
            "failure_notified": self.failure_notified,
            "last_heartbeat": self.last_heartbeat,
            "week_runs": self.week_runs,
            "week_items": self.week_items,
            "week_alerts": self.week_alerts,
            "last_briefing_date": self.last_briefing_date,
            "last_uncertainty_date": self.last_uncertainty_date,
            "reported_events": self.reported_events,
            "move_marks": self.move_marks,
            "last_eval_price": self.last_eval_price,
            "last_eval_time": self.last_eval_time,
            "lean_log": self.lean_log,
            "last_lean": self.last_lean,
            "feed_health": self.feed_health,
        }
        with open(STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    # --- dedupe -----------------------------------------------------

    def is_new(self, item_id):
        return item_id not in self.seen

    def mark_seen(self, item_id):
        self.seen[item_id] = time.time()

    # --- varselsperrer ----------------------------------------------

    def in_cooldown(self, asset, direction, cooldown_minutes):
        key = "%s:%s" % (asset, direction)
        last = self.last_alert.get(key)
        if last is None:
            return False
        return (time.time() - last) < cooldown_minutes * 60

    def alerts_today(self):
        cutoff = time.time() - 60 * 60 * 24
        return len([t for t in self.alert_log if t > cutoff])

    def record_alert(self, asset, direction):
        now = time.time()
        self.last_alert["%s:%s" % (asset, direction)] = now
        self.alert_log.append(now)
        self.week_alerts += 1

    # --- helse ------------------------------------------------------

    def record_run(self, item_count):
        self.week_runs += 1
        self.week_items += item_count

    def record_success(self):
        """Returnerer True dersom vi nettopp kom oss opp att etter feil."""
        recovered = self.failure_notified
        self.fail_streak = 0
        self.failure_notified = False
        return recovered

    def record_failure(self, threshold):
        """Returnerer True når vi bør varsle om at verktøyet er nede.

        Berre éin gong per samanhengande feilperiode - eit knekt verktøy
        skal ikkje spamme deg kvart 20. minutt.
        """
        self.fail_streak += 1
        if self.fail_streak >= threshold and not self.failure_notified:
            self.failure_notified = True
            return True
        return False

    def briefing_due(self, today):
        return self.last_briefing_date != today

    def record_briefing(self, today):
        self.last_briefing_date = today

    def event_reported(self, today, name):
        return ("%s|%s" % (today, name)) in self.reported_events

    def record_event(self, today, name):
        # Berre dagens merke blir haldne - resten er gamle nyheiter.
        self.reported_events = dict(
            (k, v) for k, v in self.reported_events.items() if k.startswith(today))
        self.reported_events["%s|%s" % (today, name)] = time.time()

    def move_mark(self, today):
        """Største rørslenivå vi alt har meldt om i dag."""
        return float(self.move_marks.get(today, 0.0))

    def record_move(self, today, level):
        # Nullstill for nye dagar, så fila ikkje veks.
        self.move_marks = {today: float(level)}

    def treng_vurdering(self, pris_no, flytt_pct, maks_gap_min, toppscore, score_grense):
        """Har det hendt nok sidan sist til aa bruke pengar paa ei vurdering?

        Tre ting kan utloeyse det. Prisen har flytta seg meiningsfullt,
        det har komme ei sak som er tung nok i seg sjolv, eller det er
        saa lenge sidan sist at vi boer sjekke uansett.

        Poenget er ikkje aa spare pengar for seg sjolv. Poenget er at
        naar vi IKKJE brukar pengar paa aa vurdere det same om att, har
        vi raad til aa sjekke fem gonger saa ofte - og daa oppdagar vi
        ei roersle innan tre minutt i staden for femten.
        """
        import time as _t
        no = _t.time()
        gap = (no - self.last_eval_time) / 60.0 if self.last_eval_time else 9999

        if gap >= maks_gap_min:
            return True, "%.0f min sidan sist" % gap
        if toppscore >= score_grense:
            return True, "tung sak (score %d)" % toppscore
        if self.last_eval_price and pris_no:
            flytt = abs(pris_no / self.last_eval_price - 1) * 100
            if flytt >= flytt_pct:
                return True, "prisen har flytta %.2f %%" % flytt
        return False, ""

    def record_eval(self, pris):
        import time as _t
        self.last_eval_time = _t.time()
        if pris:
            self.last_eval_price = pris

    def leans_today(self):
        cutoff = time.time() - 60 * 60 * 24
        return len([t for t in self.lean_log if t > cutoff])

    def in_lean_cooldown(self, direction, minutes):
        last = self.last_lean.get(direction)
        return last is not None and (time.time() - last) < minutes * 60

    def record_lean(self, direction):
        now = time.time()
        self.last_lean[direction] = now
        self.lean_log.append(now)

    def uncertainty_due(self, today):
        return self.last_uncertainty_date != today

    def record_uncertainty(self, today):
        self.last_uncertainty_date = today

    # --- kjeldehelse --------------------------------------------------

    def record_feed_result(self, name, got_items):
        """Hugsar når kvar kjelde sist leverte noko."""
        entry = self.feed_health.get(name) or {}
        if got_items:
            entry["last_ok"] = time.time()
        entry["last_seen"] = time.time()
        self.feed_health[name] = entry

    def dead_feeds(self, names, quiet_days=7):
        """Kjelder som ikkje har levert ei sak på ei veke.

        Ei kjelde kan godt vere tom nokre timar. Har ho vore tom i sju
        døgn medan alle dei andre leverer, er det ikkje rolege tider -
        då er URL-en død.
        """
        cutoff = time.time() - quiet_days * 24 * 3600
        dead = []
        for name in names:
            entry = self.feed_health.get(name)
            if not entry:
                continue
            first = entry.get("last_seen", 0)
            if first and first < cutoff:
                continue  # Vi har ikkje sett henne i det heile - eige problem.
            if entry.get("last_ok", 0) < cutoff:
                dead.append(name)
        return dead

    def heartbeat_due(self, min_days=6):
        return (time.time() - self.last_heartbeat) > min_days * 24 * 3600

    def record_heartbeat(self):
        self.last_heartbeat = time.time()
        stats = (self.week_runs, self.week_items, self.week_alerts)
        self.week_runs = 0
        self.week_items = 0
        self.week_alerts = 0
        return stats
