"""Kredittrekneskapen. Dobbel bokføring, fordi alternativet blør pengar.

Tre reglar som ikkje kan brytast:

1. Kvar transaksjon har posteringar som summerer til null. Kredittar
   blir aldri skapte eller øydelagde, berre flytta. Går summen ikkje
   opp, er det ein feil i koden, ikkje i tala.

2. Kvar transaksjon har ein idempotensnøkkel. Ringer appen to gonger
   fordi nettet datt ut, skjer det éin gong. Dette er den vanlegaste
   måten slike appar mistar pengar på.

3. Kredittar blir RESERVERTE før genereringa, ikkje trekte. Feilar
   leverandøren, får brukaren dei att. Trekk-først gir sinte brukarar
   og refusjonar; reserver-først gir korrekte tal.

Saldoen er alltid summen av posteringane. Det finst ikkje eit
saldofelt som kan kome ut av takt med historikken.
"""

import sqlite3
import time
import uuid
from dataclasses import dataclass

# Systemkontoar. Desse går negative - dei har utstedt kredittane.
KONTO_GAVER = "system:gaver"
KONTO_KJOP = "system:kjop"
KONTO_FORBRUK = "system:forbruk"

RESERVASJON_OPEN = "open"
RESERVASJON_GJORT_OPP = "gjort_opp"
RESERVASJON_FRIGITT = "frigitt"

SKJEMA = """
CREATE TABLE IF NOT EXISTS transaksjon (
    id          TEXT PRIMARY KEY,
    idem        TEXT NOT NULL UNIQUE,
    slag        TEXT NOT NULL,
    brukar      TEXT,
    tid         REAL NOT NULL,
    notat       TEXT
);

CREATE TABLE IF NOT EXISTS postering (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    transaksjon_id TEXT NOT NULL REFERENCES transaksjon(id),
    konto          TEXT NOT NULL,
    belop          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_postering_konto ON postering(konto);

CREATE TABLE IF NOT EXISTS reservasjon (
    id             TEXT PRIMARY KEY,
    brukar         TEXT NOT NULL,
    kredittar      INTEGER NOT NULL,
    status         TEXT NOT NULL,
    oppretta       REAL NOT NULL,
    avslutta       REAL
);
CREATE INDEX IF NOT EXISTS idx_reservasjon_open ON reservasjon(status, oppretta);
"""


class LedgerFeil(Exception):
    """Noko er gale med rekneskapen. Aldri svelg denne."""


class ForLiteSaldo(LedgerFeil):
    def __init__(self, har, treng):
        self.har, self.treng = har, treng
        super().__init__(f"Har {har} kredittar, treng {treng}")


@dataclass(frozen=True)
class Reservasjon:
    id: str
    brukar: str
    kredittar: int
    status: str


def saldo_konto(brukar):
    return f"brukar:{brukar}:saldo"


def reservert_konto(brukar):
    return f"brukar:{brukar}:reservert"


class Ledger:
    def __init__(self, sti=":memory:"):
        # check_same_thread=False fordi ein webserver handsamar
        # foresporslar i fleire traadar. Skrivingane er serialiserte av
        # BEGIN IMMEDIATE, saa det er trygt her - men SQLite er uansett
        # berre for utvikling. Byt til Postgres foer lansering; da blir
        # BEGIN IMMEDIATE til SELECT ... FOR UPDATE.
        self.db = sqlite3.connect(sti, isolation_level=None,
                                  check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.executescript(SKJEMA)

    def close(self):
        self.db.close()

    # -- lesing ------------------------------------------------------

    def saldo(self, brukar):
        """Kva brukaren kan bruke no. Reserverte kredittar tel ikkje med."""
        return self._sum(saldo_konto(brukar))

    def reservert(self, brukar):
        return self._sum(reservert_konto(brukar))

    def _sum(self, konto):
        rad = self.db.execute(
            "SELECT COALESCE(SUM(belop), 0) AS s FROM postering WHERE konto = ?",
            (konto,),
        ).fetchone()
        return rad["s"]

    # -- skriving ----------------------------------------------------

    def gi_gave(self, brukar, kredittar, idem):
        """Gratiskredittar ved registrering. Kostar deg ekte pengar."""
        return self._flytt(idem, "gave", KONTO_GAVER, saldo_konto(brukar),
                           kredittar, brukar)

    def kjop(self, brukar, kredittar, idem):
        """Kjøpte kredittar. idem bør vere kvitteringsid-en frå Apple."""
        return self._flytt(idem, "kjop", KONTO_KJOP, saldo_konto(brukar),
                           kredittar, brukar)

    def reserver(self, brukar, kredittar, idem):
        """Hald av kredittar før generering. Feilar viss saldoen ikkje held.

        Atomisk: to samtidige kall kan ikkje begge sjå same saldo.
        BEGIN IMMEDIATE tek skrivelåsen med ein gong, ikkje ved første
        skriving. I Postgres ville dette vore SELECT ... FOR UPDATE.
        """
        if kredittar <= 0:
            raise LedgerFeil("Kan ikkje reservere null eller negativt")

        self.db.execute("BEGIN IMMEDIATE")
        try:
            eksisterande = self._finn_idem(idem)
            if eksisterande:
                rad = self.db.execute(
                    "SELECT * FROM reservasjon WHERE id = ?", (eksisterande,)
                ).fetchone()
                self.db.execute("COMMIT")
                return Reservasjon(rad["id"], rad["brukar"], rad["kredittar"],
                                   rad["status"])

            har = self._sum(saldo_konto(brukar))
            if har < kredittar:
                self.db.execute("ROLLBACK")
                raise ForLiteSaldo(har, kredittar)

            res_id = str(uuid.uuid4())
            self._skriv(res_id, idem, "reserver", brukar, [
                (saldo_konto(brukar), -kredittar),
                (reservert_konto(brukar), kredittar),
            ])
            self.db.execute(
                "INSERT INTO reservasjon (id, brukar, kredittar, status, oppretta)"
                " VALUES (?, ?, ?, ?, ?)",
                (res_id, brukar, kredittar, RESERVASJON_OPEN, time.time()),
            )
            self.db.execute("COMMIT")
            return Reservasjon(res_id, brukar, kredittar, RESERVASJON_OPEN)
        except Exception:
            try:
                self.db.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise

    def gjer_opp(self, reservasjon_id):
        """Genereringa lukkast. Kredittane er brukte for godt."""
        return self._avslutt(reservasjon_id, RESERVASJON_GJORT_OPP, KONTO_FORBRUK)

    def frigi(self, reservasjon_id):
        """Genereringa feila. Brukaren får kredittane att."""
        res = self._hent_reservasjon(reservasjon_id)
        return self._avslutt(reservasjon_id, RESERVASJON_FRIGITT,
                             saldo_konto(res["brukar"]))

    def _avslutt(self, reservasjon_id, ny_status, mot_konto):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rad = self._hent_reservasjon(reservasjon_id)
            if rad["status"] != RESERVASJON_OPEN:
                # Alt avslutta. Idempotent - ikkje ein feil, berre eit nei.
                self.db.execute("COMMIT")
                return Reservasjon(rad["id"], rad["brukar"], rad["kredittar"],
                                   rad["status"])

            brukar, kredittar = rad["brukar"], rad["kredittar"]
            self._skriv(str(uuid.uuid4()), f"avslutt:{reservasjon_id}",
                        ny_status, brukar, [
                            (reservert_konto(brukar), -kredittar),
                            (mot_konto, kredittar),
                        ])
            self.db.execute(
                "UPDATE reservasjon SET status = ?, avslutta = ? WHERE id = ?",
                (ny_status, time.time(), reservasjon_id),
            )
            self.db.execute("COMMIT")
            return Reservasjon(reservasjon_id, brukar, kredittar, ny_status)
        except Exception:
            try:
                self.db.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise

    def rydd_gamle_reservasjonar(self, eldre_enn_sekund=3600):
        """Frigi kredittar som står fast fordi ein jobb kraasja.

        Utan denne blir kredittar borte for brukaren utan at nokon
        har fått noko. Køyr han som ein cron kvart kvarter.
        """
        grense = time.time() - eldre_enn_sekund
        ider = [r["id"] for r in self.db.execute(
            "SELECT id FROM reservasjon WHERE status = ? AND oppretta < ?",
            (RESERVASJON_OPEN, grense),
        ).fetchall()]
        for res_id in ider:
            self.frigi(res_id)
        return len(ider)

    # -- internt -----------------------------------------------------

    def _flytt(self, idem, slag, fra_konto, til_konto, kredittar, brukar):
        if kredittar <= 0:
            raise LedgerFeil("Kan ikkje flytte null eller negativt")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self._finn_idem(idem):
                self.db.execute("COMMIT")
                return self._sum(saldo_konto(brukar))
            self._skriv(str(uuid.uuid4()), idem, slag, brukar, [
                (fra_konto, -kredittar),
                (til_konto, kredittar),
            ])
            self.db.execute("COMMIT")
            return self._sum(saldo_konto(brukar))
        except Exception:
            try:
                self.db.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise

    def _finn_idem(self, idem):
        rad = self.db.execute(
            "SELECT id FROM transaksjon WHERE idem = ?", (idem,)
        ).fetchone()
        return rad["id"] if rad else None

    def _skriv(self, tx_id, idem, slag, brukar, posteringar):
        if sum(b for _, b in posteringar) != 0:
            raise LedgerFeil(
                f"Posteringane summerer ikkje til null: {posteringar}")
        self.db.execute(
            "INSERT INTO transaksjon (id, idem, slag, brukar, tid)"
            " VALUES (?, ?, ?, ?, ?)",
            (tx_id, idem, slag, brukar, time.time()),
        )
        self.db.executemany(
            "INSERT INTO postering (transaksjon_id, konto, belop) VALUES (?, ?, ?)",
            [(tx_id, k, b) for k, b in posteringar],
        )

    def _hent_reservasjon(self, reservasjon_id):
        rad = self.db.execute(
            "SELECT * FROM reservasjon WHERE id = ?", (reservasjon_id,)
        ).fetchone()
        if rad is None:
            raise LedgerFeil(f"Ukjend reservasjon: {reservasjon_id}")
        return rad

    # -- kontroll ----------------------------------------------------

    def stemmer(self):
        """Summen av ALLE posteringar skal vere null. Alltid.

        Køyr denne i produksjon som ein helsesjekk. Svarar han nei,
        har du ein bug som lagar eller øydelegg kredittar.
        """
        rad = self.db.execute(
            "SELECT COALESCE(SUM(belop), 0) AS s FROM postering").fetchone()
        return rad["s"] == 0
