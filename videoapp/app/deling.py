"""Deling og verving. Dette er vekstkanalen, ikkje ein finpuss.

Med null gratiskredittar er betalt annonsering utelukka: 50 kr per
installasjon og 2 % som teiknar abonnement gir 2500 kr per abonnent,
mot rundt 55 kr i månadleg forteneste. Det går ikkje opp. Så veksten
må vere organisk, og då er delingssløyfa produktet.

Tre avgjerder som avgjer om dette blir ein kanal eller eit pengesluk:

1. BELØNNING VED HANDLING, IKKJE VED KLIKK. Betaler du når nokon opnar
   ei lenke, betaler du for bottar. Betaler du først når den nye
   brukaren faktisk har laga ein video, betaler du for ekte folk.

2. TAK PER VERVAR. Utan tak er dette eit pengetrykkeri for den som
   orkar å lage kontoar. Med tak er farming ikkje verdt bryet.

3. DELINGSTOKEN ER IKKJE JOBB-ID. Deler du den interne id-en, kan folk
   gjette seg til andre sine videoar. Delingstokenet er tilfeldig og
   seier ingenting om kva som ligg bak.
"""

import logging
import secrets
import sqlite3
import time

log = logging.getLogger(__name__)

SKJEMA = """
CREATE TABLE IF NOT EXISTS deling (
    token     TEXT PRIMARY KEY,
    jobb_id   TEXT NOT NULL,
    eigar     TEXT NOT NULL,
    oppretta  REAL NOT NULL,
    opningar  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_deling_eigar ON deling(eigar);

CREATE TABLE IF NOT EXISTS verving (
    ny_brukar   TEXT PRIMARY KEY,       -- ein brukar kan berre vervast EIN gong
    vervar      TEXT NOT NULL,
    token       TEXT,
    oppretta    REAL NOT NULL,
    belont      INTEGER NOT NULL DEFAULT 0,
    belont_tid  REAL
);
CREATE INDEX IF NOT EXISTS idx_verving_vervar ON verving(vervar, belont);
"""


class DelingFeil(Exception):
    pass


class Deling:
    def __init__(self, ledger, prisbok, sti=":memory:"):
        self.ledger = ledger
        self.prisbok = prisbok
        self.db = sqlite3.connect(sti, isolation_level=None,
                                  check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.executescript(SKJEMA)

    def close(self):
        self.db.close()

    # -- dele --------------------------------------------------------

    def lag_lenke(self, jobb_id, eigar):
        """Lag ei delelenke for ein ferdig video.

        Tokenet er tilfeldig, ikkje jobb-id-en. Deler du den interne
        id-en, kan folk telje seg fram til andre sine videoar.
        """
        rad = self.db.execute(
            "SELECT token FROM deling WHERE jobb_id = ?", (jobb_id,)).fetchone()
        if rad:
            return rad["token"]
        token = secrets.token_urlsafe(12)
        self.db.execute(
            "INSERT INTO deling (token, jobb_id, eigar, oppretta)"
            " VALUES (?, ?, ?, ?)", (token, jobb_id, eigar, time.time()))
        return token

    def opne(self, token):
        """Nokon opna ei delt lenke. Returnerer (jobb_id, eigar) eller None."""
        rad = self.db.execute(
            "SELECT * FROM deling WHERE token = ?", (token,)).fetchone()
        if rad is None:
            return None
        self.db.execute(
            "UPDATE deling SET opningar = opningar + 1 WHERE token = ?",
            (token,))
        return rad["jobb_id"], rad["eigar"]

    # -- verve -------------------------------------------------------

    def registrer(self, ny_brukar, token):
        """Ein ny brukar kom via ei delelenke. Ingen kredittar enno.

        Belønninga kjem først når han faktisk har laga noko - sjå
        `los_ut()`. Betaler vi her, betaler vi for bottar.
        """
        rad = self.db.execute(
            "SELECT eigar FROM deling WHERE token = ?", (token,)).fetchone()
        if rad is None:
            return False
        vervar = rad["eigar"]

        if vervar == ny_brukar:
            # Deler du di eiga lenke med deg sjølv, er du ikkje ein kanal.
            log.info("Sjølvverving avvist for %s", ny_brukar)
            return False

        try:
            self.db.execute(
                "INSERT INTO verving (ny_brukar, vervar, token, oppretta)"
                " VALUES (?, ?, ?, ?)",
                (ny_brukar, vervar, token, time.time()))
        except sqlite3.IntegrityError:
            # Alt verva av nokon. Første som fekk han, får han.
            return False
        return True

    def los_ut(self, ny_brukar):
        """Den nye brukaren gjorde noko ekte. No betaler vi.

        Kall denne når han har laga sin første video. Returnerer True
        dersom kredittar faktisk blei utbetalte.
        """
        rad = self.db.execute(
            "SELECT * FROM verving WHERE ny_brukar = ?", (ny_brukar,)).fetchone()
        if rad is None or rad["belont"]:
            return False

        vervar = rad["vervar"]
        if self._talet_belont(vervar) >= self.prisbok.verv_maks:
            # Taket er nådd. Vervinga står som registrert, men blir
            # ikkje betalt - elles er dette eit pengetrykkeri.
            log.info("Vervar %s har naadd taket paa %s", vervar,
                     self.prisbok.verv_maks)
            self.db.execute(
                "UPDATE verving SET belont = -1, belont_tid = ?"
                " WHERE ny_brukar = ?", (time.time(), ny_brukar))
            return False

        self.db.execute(
            "UPDATE verving SET belont = 1, belont_tid = ? WHERE ny_brukar = ?",
            (time.time(), ny_brukar))

        # Idempotensnokkelen er den nye brukaren - han kan berre verve
        # ein gong, saa kredittane kan berre betalast ein gong.
        if self.prisbok.verv_til_vervar:
            self.ledger.gi_gave(vervar, self.prisbok.verv_til_vervar,
                                idem=f"verving:vervar:{ny_brukar}")
        if self.prisbok.verv_til_ny:
            self.ledger.gi_gave(ny_brukar, self.prisbok.verv_til_ny,
                                idem=f"verving:ny:{ny_brukar}")
        return True

    def _talet_belont(self, vervar):
        rad = self.db.execute(
            "SELECT COUNT(*) AS n FROM verving WHERE vervar = ? AND belont = 1",
            (vervar,)).fetchone()
        return rad["n"]

    def statistikk(self, brukar):
        """Kva brukaren ser i appen: kor mange han har verva."""
        return {
            "belont": self._talet_belont(brukar),
            "tak": self.prisbok.verv_maks,
            "kredittar_per_verving": self.prisbok.verv_til_vervar,
        }
