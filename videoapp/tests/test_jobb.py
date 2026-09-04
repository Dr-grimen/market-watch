"""Testar for heile vegen gjennom.

Alle desse handlar om éin ting: at ingen blir trekt kredittar for ein
video dei ikkje fekk, og at ingen får ein video utan å bli trekt.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.jobb import AVVIST, FEILA, FOR_LITE, OK, Verkstad
from app.ledger import Ledger
from app.moderering import GODKJENT, Vurdering
from app.pricing import Prisbok
from app.providers.base import Leverandor, MellombelsFeil, Resultat, VarigFeil
from app.providers.router import Ruter


class FalskModerering:
    def __init__(self, vurdering=GODKJENT):
        self.vurdering = vurdering
        self.kall = 0

    def sjekk(self, prompt, bilde_b64=None, brukar=None):
        self.kall += 1
        return self.vurdering


class FalskLeverandor(Leverandor):
    def __init__(self, konfig, kastar=None):
        super().__init__(konfig, api_nokkel="test")
        self.kastar = kastar

    def generer(self, jobb):
        if self.kastar:
            raise self.kastar
        return Resultat("https://d/v.mp4", self.konfig.nokkel, jobb.sekund, 1.0)


@pytest.fixture
def oppsett(monkeypatch):
    # Promptforbetringa skal ikkje ringe ut i testane.
    monkeypatch.setattr("app.jobb.forbetre", lambda o, **kw: f"betre: {o}")
    p = Prisbok()
    lg = Ledger(":memory:")
    lg.gi_gave("ola", 100, idem="start")

    def bygg(kastar=None, vurdering=GODKJENT):
        ad = {n: FalskLeverandor(p.leverandorar[n], kastar)
              for n in p.leverandorar}
        mod = FalskModerering(vurdering)
        return Verkstad(lg, Ruter(p, ad), p, mod), lg, mod

    yield bygg
    assert lg.stemmer()
    lg.close()


def test_god_jobb_gir_video_og_trekk(oppsett):
    v, lg, _ = oppsett()
    u = v.lag_video("ola", "https://d/b.jpg", "få han til å gå")
    assert u.ok and u.video_url
    assert lg.saldo("ola") == 90
    assert lg.reservert("ola") == 0


def test_avvist_innhald_kostar_ingenting(oppsett):
    """Blir du stoppa av moderering, skal du ikkje betale for det."""
    v, lg, _ = oppsett(vurdering=Vurdering(ok=False, kategori="seksuelt",
                                           grunn="Nei."))
    u = v.lag_video("ola", "https://d/b.jpg", "noko stygt")
    assert u.status == AVVIST
    assert lg.saldo("ola") == 100, "Brukaren blei trekt for eit avslag"


def test_moderering_koeyrer_foer_trekk(oppsett):
    v, lg, mod = oppsett(vurdering=Vurdering(ok=False, grunn="Nei."))
    v.lag_video("ola", "https://d/b.jpg", "x")
    assert mod.kall == 1
    assert lg.reservert("ola") == 0


def test_leverandorfeil_gir_kredittane_att(oppsett):
    v, lg, _ = oppsett(kastar=MellombelsFeil("alle nede"))
    u = v.lag_video("ola", "https://d/b.jpg", "få han til å gå")
    assert u.status == FEILA
    assert lg.saldo("ola") == 100
    assert lg.reservert("ola") == 0, "Kredittar hengande fast"


def test_varig_feil_gir_kredittane_att(oppsett):
    """Leverandøren avviste biletet. Brukaren betaler ikkje for det."""
    v, lg, _ = oppsett(kastar=VarigFeil("avvist"))
    u = v.lag_video("ola", "https://d/b.jpg", "få han til å gå")
    assert u.status == AVVIST
    assert lg.saldo("ola") == 100


def test_uventa_kraasj_gir_kredittane_att(oppsett):
    v, lg, _ = oppsett(kastar=RuntimeError("noko heilt anna"))
    u = v.lag_video("ola", "https://d/b.jpg", "få han til å gå")
    assert u.status == FEILA
    assert lg.saldo("ola") == 100


def test_tom_saldo_gir_tydeleg_svar(oppsett):
    v, lg, _ = oppsett()
    for i in range(10):
        v.lag_video("ola", "https://d/b.jpg", "x", jobb_id=f"j{i}")
    assert lg.saldo("ola") == 0
    u = v.lag_video("ola", "https://d/b.jpg", "x", jobb_id="ein for mykje")
    assert u.status == FOR_LITE


def test_same_jobb_to_gonger_trekk_ein_gong(oppsett):
    """Appen prøver på nytt fordi nettet datt."""
    v, lg, _ = oppsett()
    v.lag_video("ola", "https://d/b.jpg", "x", jobb_id="same")
    v.lag_video("ola", "https://d/b.jpg", "x", jobb_id="same")
    assert lg.saldo("ola") == 90


def test_dyrare_nivaa_kostar_meir(oppsett):
    v, lg, _ = oppsett()
    v.lag_video("ola", "https://d/b.jpg", "x", nivaa="hd")
    assert lg.saldo("ola") == 70
