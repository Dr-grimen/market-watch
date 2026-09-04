"""Testar for vassmerket.

ffmpeg er ikkje installert i testmiljoeet, saa vi testar kommandoen som
blir bygd - ikkje sjolve rendringa. Det viktigaste her er at brukarnamn
ikkje kan skrive seg inn i ffmpeg-kommandoen.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vassmerke import VassmerkeFeil, bygg_kommando, merk, tilgjengeleg


def test_kommandoen_har_inn_og_ut():
    k = bygg_kommando("inn.mp4", "ut.mp4")
    assert "inn.mp4" in k and "ut.mp4" in k
    assert k[0] == "ffmpeg"


def test_teksten_kjem_med():
    assert "videoapp.no" in " ".join(bygg_kommando("i.mp4", "u.mp4"))


def test_kolon_i_teksten_kan_ikkje_lage_nytt_filter():
    """Ein brukar med kolon i namnet skal ikkje kunne skrive eige filter."""
    k = " ".join(bygg_kommando("i.mp4", "u.mp4", tekst="ola:drawbox=x=0"))
    assert r"\:" in k
    assert "text='ola\\:drawbox" in k


def test_apostrof_bryt_ikkje_ut():
    k = " ".join(bygg_kommando("i.mp4", "u.mp4", tekst="ola's app"))
    assert r"\'" in k


def test_prosent_blir_escapa():
    """%% er formatkodar i drawtext og ville gitt rar tekst."""
    assert r"\%" in " ".join(bygg_kommando("i.mp4", "u.mp4", tekst="100%"))


def test_argumenta_er_ei_liste_ikkje_ein_streng():
    """Liste + subprocess utan shell=True gjer skalinjeksjon umogleg."""
    k = bygg_kommando("i.mp4", "u.mp4")
    assert isinstance(k, list)
    assert all(isinstance(a, str) for a in k)


def test_manglande_fil_blir_avvist():
    with pytest.raises(VassmerkeFeil):
        bygg_kommando("", "ut.mp4")


def test_ugyldig_gjennomsikt_blir_avvist():
    with pytest.raises(VassmerkeFeil):
        bygg_kommando("i.mp4", "u.mp4", gjennomsikt=5)


def test_faststart_er_med():
    """Utan denne maa heile fila lastast foer avspeling startar."""
    assert "+faststart" in bygg_kommando("i.mp4", "u.mp4")


def test_utan_ffmpeg_kastar_i_staden_for_aa_sende_umerkt(monkeypatch):
    """Feilar lukka. Ein umerkt delt video kostar deg kanalen."""
    monkeypatch.setattr("app.vassmerke.tilgjengeleg", lambda: False)
    with pytest.raises(VassmerkeFeil):
        merk("i.mp4", "u.mp4")


def test_tilgjengeleg_svarar_utan_aa_kraasje():
    assert tilgjengeleg() in (True, False)
