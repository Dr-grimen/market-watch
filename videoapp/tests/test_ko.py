"""Testar for kø, arbeidar og rettferdig fordeling.

Den viktigaste invarianten i heile prosjektet står nedst:
INGEN JOBB SKAL ENDE UTAN AT KREDITTANE ER GJORDE OPP ELLER FRIGITTE.
Ein jobb som gir opp og held på kredittane er ein brukar som har betalt
for ingenting.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.arbeidar import Arbeidar, Bestilling
from app.jobb import AVVIST, FEILA, FOR_LITE, OK
from app.ko import FEILA as KO_FEILA, FERDIG, VENTAR, Ko
from app.ledger import Ledger
from app.moderering import GODKJENT, Vurdering
from app.pricing import Prisbok
from app.providers.base import Leverandor, MellombelsFeil, Resultat, VarigFeil
from app.providers.router import Ruter


class FalskModerering:
    def __init__(self, vurdering=GODKJENT):
        self.vurdering = vurdering

    def sjekk(self, prompt, bilde_b64=None, brukar=None):
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
def rigg(monkeypatch):
    monkeypatch.setattr("app.arbeidar.forbetre", lambda o, **kw: o)
    p = Prisbok()
    lg = Ledger(":memory:")
    ko = Ko(":memory:", maks_forsok=3)

    def bygg(kastar=None, vurdering=GODKJENT, saldo=100):
        lg.gi_gave("ola", saldo, idem=f"start:{saldo}")
        ad = {n: FalskLeverandor(p.leverandorar[n], kastar)
              for n in p.leverandorar}
        b = Bestilling(ko, lg, p, FalskModerering(vurdering))
        a = Arbeidar(ko, lg, Ruter(p, ad), p)
        return b, a, ko, lg

    yield bygg
    assert lg.stemmer()
    lg.close()
    ko.close()


# -- bestilling ------------------------------------------------------

def test_bestilling_reserverer_med_ein_gong(rigg):
    """Brukaren skal vite NO om han har raad, ikkje om ti minutt."""
    b, _, _, lg = rigg()
    jobb_id, u = b.bestill("ola", "https://d/b.jpg", "gå")
    assert u.ok and jobb_id
    assert lg.saldo("ola") == 90
    assert lg.reservert("ola") == 10


def test_avvist_innhald_kjem_aldri_i_koen(rigg):
    b, _, ko, lg = rigg(vurdering=Vurdering(ok=False, grunn="Nei."))
    jobb_id, u = b.bestill("ola", "https://d/b.jpg", "noko stygt")
    assert u.status == AVVIST and jobb_id is None
    assert ko.tal() == {}
    assert lg.saldo("ola") == 100


def test_tom_saldo_tek_jobben_ut_av_koen(rigg):
    """Elles ligg han og blir plukka opp utan reservasjon aa gjere opp."""
    b, _, ko, lg = rigg(saldo=5)
    jobb_id, u = b.bestill("ola", "https://d/b.jpg", "gå")
    assert u.status == FOR_LITE and jobb_id is None
    assert ko.tal().get(VENTAR, 0) == 0


def test_same_bestilling_to_gonger_reserverer_ein_gong(rigg):
    b, _, _, lg = rigg()
    a1, _ = b.bestill("ola", "https://d/b.jpg", "gå", idem="same")
    a2, _ = b.bestill("ola", "https://d/b.jpg", "gå", idem="same")
    assert a1 == a2
    assert lg.saldo("ola") == 90


# -- koeyring --------------------------------------------------------

def test_god_jobb_blir_gjord_opp(rigg):
    b, a, ko, lg = rigg()
    jobb_id, _ = b.bestill("ola", "https://d/b.jpg", "gå")
    u = a.koyr_ein()
    assert u.ok
    assert lg.saldo("ola") == 90 and lg.reservert("ola") == 0
    assert ko.status(jobb_id)["status"] == FERDIG


def test_tom_koe_gir_none(rigg):
    _, a, _, _ = rigg()
    assert a.koyr_ein() is None


def test_mellombels_feil_blir_proevd_igjen(rigg):
    b, a, ko, lg = rigg(kastar=MellombelsFeil("503"))
    jobb_id, _ = b.bestill("ola", "https://d/b.jpg", "gå")
    a.koyr_ein()
    assert ko.status(jobb_id)["status"] == VENTAR, "Skulle prøvd igjen"
    assert lg.reservert("ola") == 10, "Reservasjonen skal stå medan vi prøver"


def test_botnfall_frigir_kredittane(rigg):
    """DEN VIKTIGE. Gir jobben opp, skal brukaren ha pengane att."""
    b, a, ko, lg = rigg(kastar=MellombelsFeil("503"))
    jobb_id, _ = b.bestill("ola", "https://d/b.jpg", "gå")
    for _ in range(4):
        a.koyr_ein()
    assert ko.status(jobb_id)["status"] == KO_FEILA
    assert lg.saldo("ola") == 100, "Brukaren betalte for ein video han ikkje fekk"
    assert lg.reservert("ola") == 0, "Kredittar hengande fast"


def test_varig_feil_gir_opp_med_ein_gong_og_frigir(rigg):
    b, a, ko, lg = rigg(kastar=VarigFeil("avvist"))
    jobb_id, _ = b.bestill("ola", "https://d/b.jpg", "gå")
    u = a.koyr_ein()
    assert u.status == AVVIST
    assert ko.status(jobb_id)["status"] == KO_FEILA
    assert lg.saldo("ola") == 100


def test_forlaten_jobb_blir_lagd_ut_att(rigg):
    """Arbeidaren kraasja. Jobben skal ikkje staa fast for evig."""
    b, a, ko, lg = rigg()
    jobb_id, _ = b.bestill("ola", "https://d/b.jpg", "gå")
    ko.hent("arbeidar-som-kraasja")
    ko.forlaten_etter = -1
    u = a.koyr_ein()
    assert u is not None and u.ok


# -- rettferd --------------------------------------------------------

def test_ein_ivrig_brukar_blokkerer_ikkje_dei_andre(rigg):
    """Ola legg inn fem, Kari ein. Kari skal ikkje staa sist."""
    b, _, ko, lg = rigg()
    lg.gi_gave("kari", 100, idem="kari")
    for i in range(5):
        b.bestill("ola", "https://d/b.jpg", "gå", idem=f"ola{i}")
    b.bestill("kari", "https://d/b.jpg", "gå", idem="kari0")

    fyrst = ko.hent("w1")["brukar"]
    andre = ko.hent("w2")["brukar"]
    assert {fyrst, andre} == {"ola", "kari"}, (
        f"Fekk {fyrst} og {andre} - Kari maatte vente paa alle Ola sine")


def test_to_arbeidarar_faar_ikkje_same_jobb(rigg):
    b, _, ko, _ = rigg()
    for i in range(3):
        b.bestill("ola", "https://d/b.jpg", "gå", idem=f"j{i}")
    ider = {ko.hent(f"w{i}")["id"] for i in range(3)}
    assert len(ider) == 3


def test_plass_i_koe_er_talet_appen_viser(rigg):
    b, _, ko, _ = rigg()
    ider = [b.bestill("ola", "https://d/b.jpg", "gå", idem=f"j{i}")[0]
            for i in range(3)]
    assert ko.plass_i_ko(ider[0]) == 0
    assert ko.plass_i_ko(ider[2]) == 2


# -- invarianten -----------------------------------------------------

def test_ingen_kredittar_heng_igjen_uansett_kva_som_skjer(rigg):
    """Blandar suksess, mellombels feil og varig feil om kvarandre.

    Same kva utfall jobbane faar, skal summen gaa opp: ingen jobb er
    ferdig utan at reservasjonen er gjord opp eller frigitt.
    """
    p = Prisbok()
    utfall = [None, MellombelsFeil("503"), VarigFeil("nei"), None,
              MellombelsFeil("timeout")]
    b, a, ko, lg = rigg()

    for i, kastar in enumerate(utfall):
        b.bestill("ola", "https://d/b.jpg", "gå", idem=f"j{i}")

    # Kvar runde med si eiga feilmodus, fleire gonger så botnfallet slår inn.
    for kastar in utfall * 4:
        for ad in a.ruter.adaptere.values():
            ad.kastar = kastar
        a.koyr_ein()

    tal = ko.tal()
    uferdige = tal.get(VENTAR, 0) + tal.get("koyrer", 0)
    assert lg.reservert("ola") == uferdige * 10, (
        f"Reservert {lg.reservert('ola')} men berre {uferdige} jobbar "
        "er uavklarte - resten heng igjen")
    assert lg.stemmer()
