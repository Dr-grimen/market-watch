"""Testar for HTTP-laget.

Statuskodane er ikkje kosmetikk: appen viser kjøpsskjerm på 402 og
avslagsgrunn på 422. Blir dei bytta om, viser appen feil skjerm.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api import lag_app
from app.auth import lag_token
from app.arbeidar import Bestilling
from app.ko import Ko
from app.ledger import Ledger
from app.moderering import GODKJENT, Vurdering
from app.pricing import Prisbok


class FalskModerering:
    def __init__(self, vurdering=GODKJENT):
        self.vurdering = vurdering

    def sjekk(self, prompt, bilde_b64=None, brukar=None):
        return self.vurdering


@pytest.fixture
def rigg():
    p = Prisbok()
    lg = Ledger(":memory:")
    ko = Ko(":memory:")
    lg.gi_gave("ola", 100, idem="start")

    def bygg(vurdering=GODKJENT):
        b = Bestilling(ko, lg, p, FalskModerering(vurdering))
        return TestClient(lag_app(b, ko, lg, p, token_nokkel=NOKKEL)), ko, lg

    yield bygg
    lg.close()
    ko.close()


NOKKEL = "t" * 40
H = {"Authorization": "Bearer " + lag_token("ola", NOKKEL)}
H_KARI = {"Authorization": "Bearer " + lag_token("kari", NOKKEL)}


def test_bestilling_gir_202_og_jobb_id(rigg):
    c, _, _ = rigg()
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "gå"},
               headers=H)
    assert r.status_code == 202
    assert r.json()["jobb_id"]
    assert r.json()["kredittar_att"] == 90


def test_avvist_innhald_gir_422_med_grunn(rigg):
    """Appen viser denne teksten til brukaren."""
    c, _, _ = rigg(vurdering=Vurdering(ok=False, grunn="Det kan vi ikkje lage."))
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "x"},
               headers=H)
    assert r.status_code == 422
    assert "kan vi ikkje lage" in r.json()["detail"]


def test_tom_saldo_gir_402_ikkje_500(rigg):
    """402 er signalet appen brukar for aa vise kjoepsskjermen."""
    c, _, _ = rigg()
    for i in range(10):
        c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "x",
                               "idem": f"j{i}"}, headers=H)
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "x"},
               headers=H)
    assert r.status_code == 402


def test_utan_token_gir_401(rigg):
    c, _, _ = rigg()
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "gå"})
    assert r.status_code == 401


def test_kan_ikkje_sjaa_andre_sine_jobbar(rigg):
    c, _, _ = rigg()
    jobb_id = c.post("/video", json={"bilde_url": "https://d/b.jpg",
                                     "onske": "gå"}, headers=H).json()["jobb_id"]
    r = c.get(f"/video/{jobb_id}", headers=H_KARI)
    assert r.status_code == 404, "Lak informasjon om andre sine jobbar"


def test_saldo_kjem_frae_tokenet_ikkje_stien(rigg):
    """Kari faar Kari sin saldo, ikkje Ola sin - uansett kva ho ber om."""
    c, _, _ = rigg()
    c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "gå"},
           headers=H)
    assert c.get("/saldo", headers=H).json()["kredittar"] == 90
    assert c.get("/saldo", headers=H_KARI).json()["kredittar"] == 0


def test_tuklaa_token_gir_401(rigg):
    c, _, _ = rigg()
    falsk = lag_token("ola", "z" * 40)
    r = c.get("/saldo", headers={"Authorization": "Bearer " + falsk})
    assert r.status_code == 401


def test_utan_bearer_gir_401(rigg):
    c, _, _ = rigg()
    assert c.get("/saldo", headers={"Authorization": "ola"}).status_code == 401


def test_ukjent_nivaa_gir_400(rigg):
    c, _, _ = rigg()
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "gå",
                               "nivaa": "finst-ikkje"}, headers=H)
    assert r.status_code == 400


def test_for_lang_prompt_blir_avvist(rigg):
    c, _, _ = rigg()
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg",
                               "onske": "a" * 5000}, headers=H)
    assert r.status_code == 422


def test_helse_seier_om_rekneskapen_stemmer(rigg):
    c, _, _ = rigg()
    r = c.get("/helse")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_moderator_nede_gir_503_ikkje_422(rigg):
    """Skilnaden mellom "du gjorde noko gale" og "vi har eit problem".

    Feilar moderatoren vaar, skal brukaren bli bedd om aa prove igjen -
    ikkje faa beskjed om at innhaldet hans blei avvist.
    """
    c, _, _ = rigg(vurdering=Vurdering(
        ok=False, usikker=True,
        grunn="Vi klarte ikkje å sjekke innhaldet no. Prøv igjen om litt."))
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "gå"},
               headers=H)
    assert r.status_code == 503
    assert "Prøv igjen" in r.json()["detail"]
