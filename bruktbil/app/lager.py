"""Lagring. Éin handel = éi rad.

SQLite held til alt vi treng no, og gjer at ein demo overlever ein omstart.
Handelen ligg som JSON i ei kolonne; det som må søkjast på (kode, token) ligg
som eigne kolonner med indeks.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager

from .modell import Feil, Handel

STI = os.environ.get("BRUKTBIL_DB", os.path.join(os.path.dirname(__file__), "..", "handlar.db"))

SKJEMA = """
CREATE TABLE IF NOT EXISTS handel (
    id            TEXT PRIMARY KEY,
    kode          TEXT NOT NULL,
    seljar_token  TEXT NOT NULL,
    kjopar_token  TEXT NOT NULL,
    steg          TEXT NOT NULL,
    oppdatert     TEXT NOT NULL,
    data          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS handel_kode ON handel (kode);
"""


@contextmanager
def _kopling():
    kop = sqlite3.connect(STI)
    kop.row_factory = sqlite3.Row
    try:
        yield kop
        kop.commit()
    finally:
        kop.close()


def klargjer() -> None:
    with _kopling() as kop:
        kop.executescript(SKJEMA)


def lagre(h: Handel) -> Handel:
    with _kopling() as kop:
        kop.execute(
            "INSERT INTO handel (id, kode, seljar_token, kjopar_token, steg, oppdatert, data) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), ?) "
            "ON CONFLICT(id) DO UPDATE SET kode=excluded.kode, "
            "seljar_token=excluded.seljar_token, kjopar_token=excluded.kjopar_token, "
            "steg=excluded.steg, oppdatert=excluded.oppdatert, data=excluded.data",
            (
                h.id,
                h.kode,
                h.seljar.token,
                h.kjopar.token,
                h.steg,
                json.dumps(h.til_dict(), ensure_ascii=False),
            ),
        )
    return h


def hent(handel_id: str) -> Handel:
    with _kopling() as kop:
        rad = kop.execute("SELECT data FROM handel WHERE id = ?", (handel_id,)).fetchone()
    if not rad:
        raise Feil("Fann ikkje handelen.")
    return Handel.frå_dict(json.loads(rad["data"]))


def hent_med_kode(kode: str) -> Handel:
    with _kopling() as kop:
        rad = kop.execute(
            "SELECT data FROM handel WHERE kode = ? ORDER BY oppdatert DESC LIMIT 1",
            ((kode or "").strip().upper(),),
        ).fetchone()
    if not rad:
        raise Feil("Ingen handel med den koden. Sjekk at du har skrive han rett.")
    return Handel.frå_dict(json.loads(rad["data"]))


def hent_med_token(handel_id: str, rolle: str, token: str) -> Handel:
    """Tilgangskontrollen i demoen: du må ha lenka di.

    I ein app i drift loggar begge partar inn med BankID, og vi slår opp kva
    handlar fødselsnummeret deira er part i. Lenkene her er ei mellombels
    løysing som gjer at ein kan prøve flyten utan innlogging.
    """
    h = hent(handel_id)
    venta = h.part(rolle).token
    if not token or token != venta:
        raise Feil("Lenka er ikkje gyldig for denne handelen.")
    return h


def alle(grense: int = 50) -> list:
    with _kopling() as kop:
        radene = kop.execute(
            "SELECT data FROM handel ORDER BY oppdatert DESC LIMIT ?", (grense,)
        ).fetchall()
    return [Handel.frå_dict(json.loads(r["data"])) for r in radene]


def slett_alt() -> None:
    """Berre for testar."""
    with _kopling() as kop:
        kop.execute("DELETE FROM handel")
