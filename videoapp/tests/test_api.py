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
        return TestClient(lag_app(b, ko, lg, p)), ko, lg

    yield bygg
    lg.close()
    ko.close()


H = {"X-Brukar-Id": "ola"}


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


def test_utan_brukar_id_gir_401(rigg):
    c, _, _ = rigg()
    r = c.post("/video", json={"bilde_url": "https://d/b.jpg", "onske": "gå"})
    assert r.status_code == 401


def test_kan_ikkje_sjaa_andre_sine_jobbar(rigg):
    c, _, _ = rigg()
    jobb_id = c.post("/video", json={"bilde_url": "https://d/b.jpg",
                                     "onske": "gå"}, headers=H).json()["jobb_id"]
    r = c.get(f"/video/{jobb_id}", headers={"X-Brukar-Id": "kari"})
    assert r.status_code == 404, "Lak informasjon om andre sine jobbar"


def test_kan_ikkje_sjaa_andre_sin_saldo(rigg):
    c, _, _ = rigg()
    assert c.get("/saldo/ola", headers={"X-Brukar-Id": "kari"}).status_code == 403


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
