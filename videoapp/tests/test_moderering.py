"""Testar for portvakta.

Det viktigaste: ho skal seie NEI når ho ikkje veit. Promptforbetringa
feilar open, denne feilar lukka. Det er med vilje.
"""

import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.moderering import Moderering


class Blokk:
    type = "text"

    def __init__(self, t):
        self.text = t


class Svar:
    def __init__(self, t):
        self.content = [Blokk(t)]


class Klient:
    def __init__(self, svar=None, kastar=None):
        self.svar, self.kastar = svar, kastar
        self.messages = self
        self.kall = []

    def create(self, **kw):
        self.kall.append(kw)
        if self.kastar:
            raise self.kastar
        return Svar(self.svar)


def test_godkjent():
    m = Moderering(klient=Klient('{"ok": true}'))
    assert m.sjekk("katt som dansar").ok


def test_avvist_med_kategori():
    m = Moderering(klient=Klient(
        '{"ok": false, "kategori": "seksuelt", "grunn": "Nei."}'))
    v = m.sjekk("x")
    assert not v.ok
    assert v.kategori == "seksuelt"
    assert not v.meldepliktig


def test_barn_er_meldepliktig():
    m = Moderering(klient=Klient(
        '{"ok": false, "kategori": "barn", "grunn": "Nei."}'))
    v = m.sjekk("x")
    assert not v.ok
    assert v.meldepliktig


def test_nede_gir_nei_ikkje_ja():
    """Kan vi ikkje sjekke, lagar vi ingenting. Aldri eit ja utan dekning."""
    m = Moderering(klient=Klient(kastar=anthropic.APIConnectionError(request=None)))
    v = m.sjekk("heilt uskuldig katt")
    assert not v.ok
    assert v.usikker


def test_uleseleg_svar_gir_nei():
    m = Moderering(klient=Klient("eh, kanskje?"))
    v = m.sjekk("x")
    assert not v.ok
    assert v.usikker


def test_ukjend_kategori_er_framleis_nei():
    """Modellen sa nei med ein kategori vi ikkje kjenner. Neiet gjeld."""
    m = Moderering(klient=Klient(
        '{"ok": false, "kategori": "tull", "grunn": "Nei."}'))
    v = m.sjekk("x")
    assert not v.ok
    assert v.kategori == ""


def test_toler_kodeblokk_rundt_json():
    m = Moderering(klient=Klient('```json\n{"ok": true}\n```'))
    assert m.sjekk("x").ok


def test_bilde_blir_sendt_med():
    k = Klient('{"ok": true}')
    Moderering(klient=k).sjekk("x", bilde_b64="QUJD", bilde_type="image/png")
    innhald = k.kall[0]["messages"][0]["content"]
    assert innhald[0]["type"] == "image"
    assert innhald[0]["source"]["media_type"] == "image/png"


def test_avslag_blir_logga_utan_bilete(tmp_path):
    sti = tmp_path / "mod.jsonl"
    m = Moderering(klient=Klient(
        '{"ok": false, "kategori": "ulovleg", "grunn": "Nei."}'),
        logg_sti=sti)
    m.sjekk("x", bilde_b64="QUJD", brukar="ola")
    rad = json.loads(sti.read_text(encoding="utf-8").strip())
    assert rad["brukar"] == "ola"
    assert rad["kategori"] == "ulovleg"
    assert rad["hadde_bilde"] is True
    assert "QUJD" not in sti.read_text(encoding="utf-8")
