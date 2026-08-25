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

    def heartbeat_due(self, min_days=6):
        return (time.time() - self.last_heartbeat) > min_days * 24 * 3600

    def record_heartbeat(self):
        self.last_heartbeat = time.time()
        stats = (self.week_runs, self.week_items, self.week_alerts)
        self.week_runs = 0
        self.week_items = 0
        self.week_alerts = 0
        return stats
