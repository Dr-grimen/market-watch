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


def test_billegaste_nivaa_gaar_paa_billegaste_leverandor(p):
    rask = p.nivaa["rask"]
    assert rask.tving_billegast
    billegast_totalt = min(
        (l for l in p.leverandorar.values() if l.aktiv),
        key=lambda l: l.usd_per_second)
    vald = p.billegaste("rask")
    assert vald.usd_per_second == billegast_totalt.usd_per_second, (
        f"Rask-nivået går på {vald.nokkel}, men {billegast_totalt.nokkel} "
        "er billegare.")


def test_gratisgaava_er_null_eller_daekker_ein_video(p):
    """Anten gir vi ingenting, eller nok til å faktisk lage noko.

    Mellomtinget - nokre kredittar som ikkje rekk til ein video - er
    det verste: du betaler for lagring og støtte, brukaren får ingenting,
    og første inntrykk er at appen berre vil ha pengar.
    """
    if p.gave_ved_registrering == 0:
        return
    billegaste_video = min(n.kredittar for n in p.nivaa.values())
    assert p.gave_ved_registrering >= billegaste_video, (
        f"Nye brukarar får {p.gave_ved_registrering} kredittar, men den "
        f"billegaste videoen kostar {billegaste_video}.")


def test_abonnement_gaar_i_pluss_paa_kvart_nivaa(p):
    """Verste fall: abonnenten brukar HEILE kvota på det dyraste nivået.

    Dette er grunnen til at kvota er i kredittar og ikkje i videoar.
    Lovar du "25 videoar", kan abonnenten veksle dei inn i HD og bli
    ulønsam. Med kredittar kostar ein HD-video tre gonger så mykje av
    kvota, og rekninga går opp uansett kva han vel.
    """
    for nokkel in p.nivaa:
        a = p.abonnement(nokkel, forsok=FORSOK)
        margin = a["verste_forteneste"] / a["netto"]
        assert margin >= p.abo_minste_margin_verstefall, (
            f"Ein abonnent som brukar heile kvota på {nokkel!r} gir "
            f"{margin:.1%} margin, krev "
            f"{p.abo_minste_margin_verstefall:.0%}. Anten kostar nivået "
            "for få kredittar, eller kvota er for stor.")


def test_abonnement_taaler_kravstore_brukarar(p):
    """Same test, men med folk som regenererer mykje."""
    for nokkel in p.nivaa:
        a = p.abonnement(nokkel, forsok=FORSOK_VERSTEFALL)
        assert a["verste_forteneste"] > 0, (
            f"Abonnent som brukar alt på {nokkel!r} og regenererer "
            f"{FORSOK_VERSTEFALL}x TAPAR {-a['verste_forteneste']:.0f} kr.")


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
