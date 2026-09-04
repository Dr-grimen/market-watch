"""Testar for kredittledgeren.

Desse handlar om éin ting: at ingen kan bruke kredittar dei ikkje har,
og at ingen blir trekte to gonger. Alt anna er detaljar.
"""

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ledger import Ledger, ForLiteSaldo, LedgerFeil, RESERVASJON_OPEN


@pytest.fixture
def ledger():
    lg = Ledger(":memory:")
    yield lg
    assert lg.stemmer(), "Posteringane summerer ikkje til null"
    lg.close()


def test_gave_gir_saldo(ledger):
    ledger.gi_gave("ola", 20, idem="reg:ola")
    assert ledger.saldo("ola") == 20


def test_same_gave_to_gonger_gir_ikkje_dobbelt(ledger):
    """Appen prøver på nytt fordi nettet datt. Brukaren skal ikkje få 40."""
    ledger.gi_gave("ola", 20, idem="reg:ola")
    ledger.gi_gave("ola", 20, idem="reg:ola")
    assert ledger.saldo("ola") == 20


def test_kjop_med_same_kvittering_tel_ein_gong(ledger):
    """Apple sender same kvittering fleire gonger. Det er normalt."""
    ledger.kjop("ola", 250, idem="apple:txn-abc")
    ledger.kjop("ola", 250, idem="apple:txn-abc")
    assert ledger.saldo("ola") == 250


def test_reservasjon_flyttar_ut_av_saldo(ledger):
    ledger.gi_gave("ola", 20, idem="reg:ola")
    res = ledger.reserver("ola", 10, idem="jobb:1")
    assert ledger.saldo("ola") == 10
    assert ledger.reservert("ola") == 10
    assert res.status == RESERVASJON_OPEN


def test_kan_ikkje_reservere_meir_enn_ein_har(ledger):
    ledger.gi_gave("ola", 20, idem="reg:ola")
    with pytest.raises(ForLiteSaldo):
        ledger.reserver("ola", 21, idem="jobb:1")
    assert ledger.saldo("ola") == 20


def test_oppgjer_brenner_kredittane(ledger):
    ledger.gi_gave("ola", 20, idem="reg:ola")
    res = ledger.reserver("ola", 10, idem="jobb:1")
    ledger.gjer_opp(res.id)
    assert ledger.saldo("ola") == 10
    assert ledger.reservert("ola") == 0


def test_frigiving_gir_kredittane_att(ledger):
    """Leverandøren feila. Brukaren skal ikkje betale for det."""
    ledger.gi_gave("ola", 20, idem="reg:ola")
    res = ledger.reserver("ola", 10, idem="jobb:1")
    ledger.frigi(res.id)
    assert ledger.saldo("ola") == 20
    assert ledger.reservert("ola") == 0


def test_dobbelt_oppgjer_trekk_ikkje_to_gonger(ledger):
    ledger.gi_gave("ola", 20, idem="reg:ola")
    res = ledger.reserver("ola", 10, idem="jobb:1")
    ledger.gjer_opp(res.id)
    ledger.gjer_opp(res.id)
    assert ledger.saldo("ola") == 10


def test_kan_ikkje_frigi_etter_oppgjer(ledger):
    """Elles kunne ein brukar fått kredittane att for ein video han har."""
    ledger.gi_gave("ola", 20, idem="reg:ola")
    res = ledger.reserver("ola", 10, idem="jobb:1")
    ledger.gjer_opp(res.id)
    ledger.frigi(res.id)
    assert ledger.saldo("ola") == 10


def test_same_jobb_reserverer_berre_ein_gong(ledger):
    ledger.gi_gave("ola", 20, idem="reg:ola")
    a = ledger.reserver("ola", 10, idem="jobb:1")
    b = ledger.reserver("ola", 10, idem="jobb:1")
    assert a.id == b.id
    assert ledger.saldo("ola") == 10


def test_rydding_frigir_fastlaaste_kredittar(ledger):
    """Ein jobb kraasja. Kredittane skal ikkje bli borte for brukaren."""
    ledger.gi_gave("ola", 20, idem="reg:ola")
    ledger.reserver("ola", 10, idem="jobb:1")
    assert ledger.rydd_gamle_reservasjonar(eldre_enn_sekund=-1) == 1
    assert ledger.saldo("ola") == 20


def test_negative_belop_blir_avvist(ledger):
    with pytest.raises(LedgerFeil):
        ledger.gi_gave("ola", -5, idem="juks")
    with pytest.raises(LedgerFeil):
        ledger.reserver("ola", 0, idem="juks2")


def test_samtidige_reservasjonar_kan_ikkje_overtrekke(tmp_path):
    """Kappløpet som gir gratis videoar.

    Ti trådar prøver å reservere 10 kredittar kvar frå ein saldo på 50.
    Nøyaktig fem skal lukkast. Les alle saldoen før nokon skriv, blir
    det ti - og du har gitt bort fem videoar.
    """
    sti = str(tmp_path / "ledger.db")
    oppsett = Ledger(sti)
    oppsett.gi_gave("ola", 50, idem="reg:ola")
    oppsett.close()

    resultat = []
    laas = threading.Lock()

    def proev(n):
        lg = Ledger(sti)
        lg.db.execute("PRAGMA busy_timeout = 5000")
        try:
            lg.reserver("ola", 10, idem=f"jobb:{n}")
            with laas:
                resultat.append(True)
        except ForLiteSaldo:
            with laas:
                resultat.append(False)
        finally:
            lg.close()

    traadar = [threading.Thread(target=proev, args=(n,)) for n in range(10)]
    for t in traadar:
        t.start()
    for t in traadar:
        t.join()

    kontroll = Ledger(sti)
    try:
        assert sum(resultat) == 5, f"{sum(resultat)} lukkast, venta 5"
        assert kontroll.saldo("ola") == 0
        assert kontroll.reservert("ola") == 50
        assert kontroll.stemmer()
    finally:
        kontroll.close()
