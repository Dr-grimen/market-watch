"""Testar for ruting og failover.

Det som betyr noko: at billegast blir vald, at ein leverandør som er
nede ikkje tek ned appen, og at eit avvist bilde ikkje blir sendt til
alle fire.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pricing import Prisbok
from app.providers.base import Jobb, Leverandor, MellombelsFeil, Resultat, VarigFeil
from app.providers.router import IngenLeverandor, Ruter, Straumbrytar


class FalskLeverandor(Leverandor):
    """Ein leverandør som gjer som han får beskjed."""

    def __init__(self, konfig, kastar=None):
        super().__init__(konfig, api_nokkel="test")
        self.kastar = kastar
        self.kall = 0

    def generer(self, jobb):
        self.kall += 1
        if self.kastar:
            raise self.kastar
        return Resultat(video_url="https://d/v.mp4", leverandor=self.konfig.nokkel,
                        sekund=jobb.sekund, kostnad_nok=1.0)


@pytest.fixture
def prisbok():
    return Prisbok()


def jobb():
    return Jobb(bilde_url="https://d/b.jpg", prompt="få han til å gå",
                sekund=5, boette="medium")


def lag_ruter(prisbok, oppsett):
    adaptere = {n: FalskLeverandor(prisbok.leverandorar[n], k)
                for n, k in oppsett.items()}
    return Ruter(prisbok, adaptere), adaptere


def test_vel_billegaste(prisbok):
    ruter, ad = lag_ruter(prisbok, {
        "seedance_lite": None,
        "minimax_hailuo_fast": None,
        "minimax_hailuo_02": None,
    })
    res = ruter.generer(jobb(), "standard")
    assert res.leverandor == "seedance_lite"
    assert ad["minimax_hailuo_fast"].kall == 0


def test_fell_over_til_nest_billegaste(prisbok):
    """Billegaste er nede. Brukaren skal likevel få videoen sin."""
    ruter, ad = lag_ruter(prisbok, {
        "seedance_lite": MellombelsFeil("503"),
        "minimax_hailuo_fast": None,
    })
    res = ruter.generer(jobb(), "standard")
    assert res.leverandor == "minimax_hailuo_fast"
    assert ad["seedance_lite"].kall == 1


def test_varig_feil_stoppar_med_ein_gong(prisbok):
    """Avvist bilde skal ikkje sendast til fire leverandørar."""
    ruter, ad = lag_ruter(prisbok, {
        "seedance_lite": VarigFeil("moderering avviste biletet"),
        "minimax_hailuo_fast": None,
    })
    with pytest.raises(VarigFeil):
        ruter.generer(jobb(), "standard")
    assert ad["minimax_hailuo_fast"].kall == 0, "Skulle ikkje ha prøvd nummer to"


def test_alle_nede_gir_tydeleg_feil(prisbok):
    ruter, _ = lag_ruter(prisbok, {
        "seedance_lite": MellombelsFeil("503"),
        "minimax_hailuo_fast": MellombelsFeil("503"),
        "minimax_hailuo_02": MellombelsFeil("503"),
    })
    with pytest.raises(IngenLeverandor):
        ruter.generer(jobb(), "standard")


def test_leverandor_utan_nokkel_blir_hoppa_over(prisbok):
    ruter, ad = lag_ruter(prisbok, {"seedance_lite": None,
                                    "minimax_hailuo_fast": None})
    ad["seedance_lite"].api_nokkel = None
    res = ruter.generer(jobb(), "standard")
    assert res.leverandor == "minimax_hailuo_fast"


def test_straumbrytar_stenger_ute_etter_nok_feil():
    b = Straumbrytar(feil_for_bryt=3, kvile=60)
    for _ in range(2):
        b.feila("x")
    assert not b.open("x")
    b.feila("x")
    assert b.open("x"), "Skulle vore utestengd etter tre feil"


def test_straumbrytar_slepp_inn_igjen_etter_kvile():
    b = Straumbrytar(feil_for_bryt=1, kvile=-1)   # kvila er alt over
    b.feila("x")
    assert not b.open("x")


def test_suksess_nullstiller_straumbrytaren():
    b = Straumbrytar(feil_for_bryt=3)
    b.feila("x")
    b.feila("x")
    b.lukkast("x")
    b.feila("x")
    assert not b.open("x"), "Teljaren skulle vore nullstilt"


def test_utestengd_leverandor_blir_hoppa_over(prisbok):
    ruter, ad = lag_ruter(prisbok, {"seedance_lite": None,
                                    "minimax_hailuo_fast": None})
    for _ in range(5):
        ruter.brytar.feila("seedance_lite")
    res = ruter.generer(jobb(), "standard")
    assert res.leverandor == "minimax_hailuo_fast"
    assert ad["seedance_lite"].kall == 0
