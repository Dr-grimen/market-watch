"""Testar for deling og verving.

Desse er farmingforsoek. Eit vervesystem utan tak og utan sperrer er
eit pengetrykkeri, og pengane er dine.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.deling import Deling
from app.ledger import Ledger
from app.pricing import Prisbok


@pytest.fixture
def d():
    lg = Ledger(":memory:")
    p = Prisbok()
    deling = Deling(lg, p, ":memory:")
    yield deling, lg, p
    assert lg.stemmer()
    deling.close()
    lg.close()


def _verv(deling, vervar, ny, jobb="j1"):
    t = deling.lag_lenke(jobb, vervar)
    deling.registrer(ny, t)
    return deling.los_ut(ny)


# -- deling ----------------------------------------------------------

def test_delelenke_er_ikkje_jobb_id(d):
    """Deler du jobb-id-en, kan folk telje seg til andre sine videoar."""
    deling, _, _ = d
    t = deling.lag_lenke("jobb-123", "ola")
    assert t != "jobb-123" and len(t) > 10


def test_same_jobb_gir_same_lenke(d):
    deling, _, _ = d
    assert deling.lag_lenke("j1", "ola") == deling.lag_lenke("j1", "ola")


def test_ukjent_token_gir_none(d):
    deling, _, _ = d
    assert deling.opne("finst-ikkje") is None


def test_opning_blir_talt(d):
    deling, _, _ = d
    t = deling.lag_lenke("j1", "ola")
    deling.opne(t)
    deling.opne(t)
    rad = deling.db.execute(
        "SELECT opningar FROM deling WHERE token = ?", (t,)).fetchone()
    assert rad["opningar"] == 2


# -- verving ---------------------------------------------------------

def test_verving_betaler_begge(d):
    deling, lg, p = d
    assert _verv(deling, "ola", "kari") is True
    assert lg.saldo("ola") == p.verv_til_vervar
    assert lg.saldo("kari") == p.verv_til_ny


def test_klikk_aleine_gir_ingen_kredittar(d):
    """Betaler du paa klikk, betaler du for bottar."""
    deling, lg, _ = d
    t = deling.lag_lenke("j1", "ola")
    deling.registrer("kari", t)
    assert lg.saldo("ola") == 0, "Betalte foer kari gjorde noko"
    assert deling.los_ut("kari") is True
    assert lg.saldo("ola") > 0


def test_kan_ikkje_verve_seg_sjolv(d):
    deling, lg, _ = d
    t = deling.lag_lenke("j1", "ola")
    assert deling.registrer("ola", t) is False
    assert lg.saldo("ola") == 0


def test_ein_brukar_kan_berre_vervast_ein_gong(d):
    """Kari kan ikkje brukast om att av fleire vervarar."""
    deling, lg, p = d
    deling.registrer("kari", deling.lag_lenke("j1", "ola"))
    assert deling.registrer("kari", deling.lag_lenke("j2", "per")) is False
    deling.los_ut("kari")
    assert lg.saldo("ola") == p.verv_til_vervar
    assert lg.saldo("per") == 0


def test_dobbel_utloesing_betaler_ein_gong(d):
    deling, lg, p = d
    t = deling.lag_lenke("j1", "ola")
    deling.registrer("kari", t)
    assert deling.los_ut("kari") is True
    assert deling.los_ut("kari") is False
    assert lg.saldo("ola") == p.verv_til_vervar


def test_taket_stoppar_farming(d):
    """Utan tak er dette eit pengetrykkeri for den som lagar kontoar."""
    deling, lg, p = d
    for i in range(p.verv_maks + 10):
        _verv(deling, "farmar", f"botte{i}", jobb=f"j{i}")
    assert lg.saldo("farmar") == p.verv_maks * p.verv_til_vervar
    assert deling.statistikk("farmar")["belont"] == p.verv_maks


def test_utloesing_utan_verving_gir_ingenting(d):
    deling, lg, _ = d
    assert deling.los_ut("ukjend") is False
    assert lg.saldo("ukjend") == 0


def test_statistikk_er_det_appen_viser(d):
    deling, _, p = d
    _verv(deling, "ola", "kari")
    s = deling.statistikk("ola")
    assert s == {"belont": 1, "tak": p.verv_maks,
                 "kredittar_per_verving": p.verv_til_vervar}


# -- oekonomien ------------------------------------------------------

def test_verving_er_billegare_enn_kjopt_installasjon(d):
    """Heile grunngjevinga for at dette finst."""
    _, _, p = d
    kostnad = ((p.verv_til_vervar + p.verv_til_ny) / p.nivaa["standard"].kredittar
               * p.pris_per_levert_video("standard"))
    assert kostnad < 20, (
        f"Ei verving kostar {kostnad:.0f} kr. Da er han ikkje lenger "
        "opplagt billegare enn ein kjoept installasjon (30-80 kr).")
