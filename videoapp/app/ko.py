"""Køen. Dette er svaret på «kan millionar bruke appen samtidig».

Å ta imot millionar av brukarar er lett. Det vanskelege er at ein
generering tek eit minutt, og at leverandøren berre lèt deg køyre eit
titals om gongen. Med 1 million brukarar som lagar éin video dagleg er
det tolv i sekundet - altså sju hundre samtidige jobbar. Ingen gir deg
det. Så jobbane må stå i kø, og brukaren må få beskjed når han er klar
i staden for å vente i appen.

Fire ting denne køen gjer som ein naiv kø ikkje gjer:

1. RETTFERDIG FORDELING. Legg éin brukar inn hundre jobbar, skal han
   ikkje blokkere alle andre. Vi hentar alltid frå den brukaren som har
   færrast jobbar i arbeid akkurat no. Utan dette held ein einaste
   ivrig brukar heile køen for seg sjølv.

2. ATOMISK UTTAK. To arbeidarar kan ikkje få same jobb. Same problemet
   som i ledgeren, same løysinga.

3. GJENOPPRETTING. Ein arbeidar som kræsjar midt i ein jobb held han
   ikkje for evig. Jobbar som har stått for lenge i arbeid blir lagde
   ut att.

4. BOTNFALL. Ein jobb som feilar for mange gonger blir lagd til side i
   staden for å gå rundt i ring. Og då MÅ kredittane frigivast - ein
   jobb som gir opp utan å frigi er ein brukar som har betalt for
   ingenting.
"""

import json
import logging
import sqlite3
import time
import uuid

log = logging.getLogger(__name__)

VENTAR = "ventar"
KOYRER = "koyrer"
FERDIG = "ferdig"
FEILA = "feila"          # gav opp - kredittane er frigitte

MAKS_FORSOK = 3
# Ein jobb som har vore i arbeid lenger enn dette reknar vi som forlaten.
FORLATEN_ETTER = 900

SKJEMA = """
CREATE TABLE IF NOT EXISTS jobb (
    id             TEXT PRIMARY KEY,
    idem           TEXT NOT NULL UNIQUE,
    brukar         TEXT NOT NULL,
    nivaa          TEXT NOT NULL,
    bilde_url      TEXT NOT NULL,
    onske          TEXT NOT NULL,
    status         TEXT NOT NULL,
    forsok         INTEGER NOT NULL DEFAULT 0,
    arbeidar       TEXT,
    klaimet        REAL,
    oppretta       REAL NOT NULL,
    avslutta       REAL,
    reservasjon_id TEXT,
    video_url      TEXT,
    grunn          TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobb_koe ON jobb(status, oppretta);
CREATE INDEX IF NOT EXISTS idx_jobb_brukar ON jobb(brukar, status);
"""


class Ko:
    def __init__(self, sti=":memory:", maks_forsok=MAKS_FORSOK,
                 forlaten_etter=FORLATEN_ETTER):
        self.db = sqlite3.connect(sti, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SKJEMA)
        self.maks_forsok = maks_forsok
        self.forlaten_etter = forlaten_etter

    def close(self):
        self.db.close()

    # -- legge inn ---------------------------------------------------

    def legg_til(self, brukar, bilde_url, onske, nivaa="standard", idem=None):
        """Set ein jobb i kø. Same idem to gonger gir same jobben."""
        idem = idem or str(uuid.uuid4())
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rad = self.db.execute(
                "SELECT id FROM jobb WHERE idem = ?", (idem,)).fetchone()
            if rad:
                self.db.execute("COMMIT")
                return rad["id"]
            jobb_id = str(uuid.uuid4())
            self.db.execute(
                "INSERT INTO jobb (id, idem, brukar, nivaa, bilde_url, onske,"
                " status, oppretta) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (jobb_id, idem, brukar, nivaa, bilde_url, onske, VENTAR,
                 time.time()))
            self.db.execute("COMMIT")
            return jobb_id
        except Exception:
            self._rull_tilbake()
            raise

    # -- ta ut -------------------------------------------------------

    def hent(self, arbeidar):
        """Ta ut neste jobb, eller None.

        Rettferdig: vi vel frå den brukaren som har færrast jobbar i
        arbeid no. Er det likt, tek vi den eldste. Slik kjem ein brukar
        med hundre jobbar i kø aldri framfor ein som har éin.
        """
        self._legg_ut_forlatne()

        self.db.execute("BEGIN IMMEDIATE")
        try:
            rad = self.db.execute("""
                SELECT j.id,
                       (SELECT COUNT(*) FROM jobb k
                         WHERE k.brukar = j.brukar AND k.status = ?) AS i_arbeid
                  FROM jobb j
                 WHERE j.status = ?
                 ORDER BY i_arbeid ASC, j.oppretta ASC
                 LIMIT 1
            """, (KOYRER, VENTAR)).fetchone()

            if rad is None:
                self.db.execute("COMMIT")
                return None

            self.db.execute(
                "UPDATE jobb SET status = ?, arbeidar = ?, klaimet = ?,"
                " forsok = forsok + 1 WHERE id = ?",
                (KOYRER, arbeidar, time.time(), rad["id"]))
            jobb = self._hent(rad["id"])
            self.db.execute("COMMIT")
            return jobb
        except Exception:
            self._rull_tilbake()
            raise

    def _legg_ut_forlatne(self):
        """Arbeidaren kræsja. Jobben skal ikkje stå fast for evig."""
        grense = time.time() - self.forlaten_etter
        self.db.execute(
            "UPDATE jobb SET status = ?, arbeidar = NULL, klaimet = NULL"
            " WHERE status = ? AND klaimet < ?",
            (VENTAR, KOYRER, grense))

    # -- avslutte ----------------------------------------------------

    def fullfor(self, jobb_id, video_url, reservasjon_id=None):
        self.db.execute(
            "UPDATE jobb SET status = ?, video_url = ?, avslutta = ?,"
            " reservasjon_id = COALESCE(?, reservasjon_id) WHERE id = ?",
            (FERDIG, video_url, time.time(), reservasjon_id, jobb_id))

    def feila(self, jobb_id, grunn, kan_prove_igjen=True):
        """Meld at eit forsøk gjekk gale.

        Returnerer True dersom jobben går i kø igjen, False dersom han
        gav opp. Gav han opp, MÅ den som kalla frigi kredittane.
        """
        rad = self._hent(jobb_id)
        if rad is None:
            return False

        gir_opp = (not kan_prove_igjen) or rad["forsok"] >= self.maks_forsok
        if gir_opp:
            self.db.execute(
                "UPDATE jobb SET status = ?, grunn = ?, avslutta = ?,"
                " arbeidar = NULL WHERE id = ?",
                (FEILA, grunn, time.time(), jobb_id))
            log.warning("Jobb %s gav opp etter %s forsøk: %s",
                        jobb_id, rad["forsok"], grunn)
            return False

        self.db.execute(
            "UPDATE jobb SET status = ?, grunn = ?, arbeidar = NULL,"
            " klaimet = NULL WHERE id = ?",
            (VENTAR, grunn, jobb_id))
        return True

    # -- lesing ------------------------------------------------------

    def status(self, jobb_id):
        rad = self._hent(jobb_id)
        return dict(rad) if rad else None

    def plass_i_ko(self, jobb_id):
        """Kor mange står føre? Dette er talet appen viser brukaren."""
        rad = self._hent(jobb_id)
        if rad is None or rad["status"] != VENTAR:
            return 0
        n = self.db.execute(
            "SELECT COUNT(*) AS n FROM jobb WHERE status = ? AND oppretta < ?",
            (VENTAR, rad["oppretta"])).fetchone()
        return n["n"]

    def tal(self):
        rader = self.db.execute(
            "SELECT status, COUNT(*) AS n FROM jobb GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rader}

    def _hent(self, jobb_id):
        return self.db.execute(
            "SELECT * FROM jobb WHERE id = ?", (jobb_id,)).fetchone()

    def _rull_tilbake(self):
        try:
            self.db.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
