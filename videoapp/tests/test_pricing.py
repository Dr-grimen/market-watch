"""Testar for prisar og marginar.

Desse er annleis enn dei andre: dei testar ikkje kode, dei testar
FORRETNINGA. Set nokon kredittprisen for lågt i providers.yaml, skal
bygget seie ifrå - ikkje rekneskapen tre månader seinare.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pricing import KonfigFeil, Prisbok

# Kor mange genereringar som i snitt går med per levert video.
# Bilde-til-video med fast lengd ligg lågt fordi folk godtek første
# forsøk. Endrar dette seg i produksjon, endre talet her - marginane
# under følgjer med.
FORSOK = 1.3

# Verste realistiske tilfelle: kravstore brukarar som masar.
FORSOK_VERSTEFALL = 2.5


@pytest.fixture
def p():
    return Prisbok()


def test_alle_nivaa_tener_pengar(p):
    for nokkel in p.nivaa:
        m = p.margin(nokkel, forsok=FORSOK)
        assert m.margin >= p.minste_margin, (
            f"Nivået {nokkel!r} har {m.margin:.1%} margin, krev "
            f"{p.minste_margin:.0%}. Auk kredittprisen eller finn ein "
            f"billegare leverandør.")


def test_ingen_nivaa_tapar_pengar_i_verstefall(p):
    """Sjølv om folk regenererer mykje, skal vi ikkje betale for å levere."""
    for nokkel in p.nivaa:
        m = p.margin(nokkel, forsok=FORSOK_VERSTEFALL)
        assert m.bruttofortenest > 0, (
            f"Nivået {nokkel!r} TAPAR {-m.bruttofortenest:.2f} kr per video "
            f"når folk regenererer {FORSOK_VERSTEFALL} gonger.")


def test_dyraste_leverandor_er_ogsaa_forsvarleg(p):
    """Failover må ikkje snu ein god margin til eit tap.

    Fell vi over til dyraste leverandør ein heil dag fordi den billege
    er nede, skal vi framleis ikkje betale for å levere.
    """
    for nokkel in p.nivaa:
        for lev in p.kandidatar(nokkel):
            m = p.margin(nokkel, lev.nokkel, forsok=FORSOK)
            assert m.bruttofortenest > 0, (
                f"Failover til {lev.nokkel} på {nokkel!r} gir tap.")


def test_kvart_nivaa_har_minst_ein_leverandor(p):
    for nokkel in p.nivaa:
        assert p.kandidatar(nokkel), f"Ingen leverandør klarer {nokkel!r}"


def test_gratisnivaaet_gaar_paa_det_billegaste(p):
    """Gratisbrenn er den største enkeltrisikoen. Han skal vere minst mogleg."""
    gratis = p.nivaa["gratis"]
    assert gratis.tving_billegast
    billegast_totalt = min(
        (l for l in p.leverandorar.values() if l.aktiv),
        key=lambda l: l.usd_per_second)
    vald = p.billegaste("gratis")
    assert vald.usd_per_second == billegast_totalt.usd_per_second, (
        f"Gratisnivået går på {vald.nokkel}, men {billegast_totalt.nokkel} "
        "er billegare. Kvar gratisvideo kostar deg meir enn han treng.")


def test_gratisgaava_rekk_til_minst_ein_video(p):
    """Feilen i den opphavlege planen: 20 kredittar, 50 per video.

    Får ikkje ein ny brukar laga NOKO, er første inntrykk at appen
    berre vil ha pengar. Då er heile gratistrinnet bortkasta.
    """
    gratis = p.nivaa["gratis"]
    assert p.gave_ved_registrering >= gratis.kredittar, (
        f"Nye brukarar får {p.gave_ved_registrering} kredittar, men den "
        f"billegaste videoen kostar {gratis.kredittar}. Dei får ikkje "
        "laga noko som helst.")


def test_manglande_nivaa_gir_tydeleg_feil(p):
    with pytest.raises(KonfigFeil):
        p.margin("finst-ikkje")


def test_konfig_utan_aktive_leverandorar_blir_avvist(tmp_path):
    import yaml
    kjelde = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "config" / "providers.yaml")
        .read_text(encoding="utf-8"))
    for d in kjelde["leverandorar"].values():
        d["aktiv"] = False
    sti = tmp_path / "tom.yaml"
    sti.write_text(yaml.safe_dump(kjelde), encoding="utf-8")
    with pytest.raises(KonfigFeil):
        Prisbok(sti)
