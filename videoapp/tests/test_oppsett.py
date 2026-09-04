"""Testar for oppsett.

Det viktigaste: appen skal nekte aa starte utan noeklar, ikkje starte
halvvegs og feile foerst naar ein brukar proever noko.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.oppsett import Oppsett, OppsettFeil
from app.pricing import Prisbok

HEILT = {
    "VIDEOAPP_TOKEN_NOKKEL": "n" * 40,
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "MINIMAX_API_NOKKEL": "mm-test",
    "SEEDANCE_API_NOKKEL": "sd-test",
}


def test_heilt_oppsett_startar():
    o = Oppsett.frae_miljoet(HEILT)
    assert o.sjekk(Prisbok()) is o


def test_manglande_tokennokkel_stoppar_oppstart():
    m = dict(HEILT, VIDEOAPP_TOKEN_NOKKEL="")
    with pytest.raises(OppsettFeil, match="VIDEOAPP_TOKEN_NOKKEL"):
        Oppsett.frae_miljoet(m).sjekk(Prisbok())


def test_for_kort_tokennokkel_stoppar_oppstart():
    m = dict(HEILT, VIDEOAPP_TOKEN_NOKKEL="kort")
    with pytest.raises(OppsettFeil):
        Oppsett.frae_miljoet(m).sjekk(Prisbok())


def test_manglande_anthropic_stoppar_oppstart():
    """Utan moderering blir ingen videoar laga uansett - stopp med ein gong."""
    m = dict(HEILT, ANTHROPIC_API_KEY="")
    with pytest.raises(OppsettFeil, match="moderering"):
        Oppsett.frae_miljoet(m).sjekk(Prisbok())


def test_ingen_leverandornokkel_stoppar_oppstart():
    m = dict(HEILT, MINIMAX_API_NOKKEL="", SEEDANCE_API_NOKKEL="")
    with pytest.raises(OppsettFeil, match="leverandør"):
        Oppsett.frae_miljoet(m).sjekk(Prisbok())


def test_ein_einaste_leverandor_gir_aatvaring_ikkje_feil():
    """Du kan koeyre, men du har ingen failover. Det skal du faa vite."""
    m = dict(HEILT, SEEDANCE_API_NOKKEL="")
    o = Oppsett.frae_miljoet(m)
    o.sjekk(Prisbok())
    assert any(f.startswith("ÅTVARING") for f in o.manglar(Prisbok()))


def test_feilmeldinga_seier_alt_som_manglar_paa_ein_gong():
    with pytest.raises(OppsettFeil) as e:
        Oppsett.frae_miljoet({}).sjekk(Prisbok())
    tekst = str(e.value)
    assert "VIDEOAPP_TOKEN_NOKKEL" in tekst and "ANTHROPIC_API_KEY" in tekst


def test_utan_database_url_er_det_ikkje_produksjon():
    assert not Oppsett.frae_miljoet(HEILT).er_produksjon()
    assert Oppsett.frae_miljoet(
        dict(HEILT, DATABASE_URL="postgres://x")).er_produksjon()
