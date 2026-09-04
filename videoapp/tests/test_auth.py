"""Testar for token. Desse er angrepsforsøk, ikkje bruksdoeme."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import AuthFeil, hent_nokkel, lag_token, les_token

N = "x" * 40
N2 = "y" * 40


def test_rundtur():
    assert les_token(lag_token("ola", N), N) == "ola"


def test_tuklaa_kropp_blir_avvist():
    """Byter angriparen brukar-id, skal signaturen ryke."""
    from app.auth import _b64
    import json
    falsk = _b64(json.dumps({"b": "kari", "ut": 9999999999},
                            separators=(",", ":"), sort_keys=True).encode())
    ekte_sig = lag_token("ola", N).split(".")[1]
    with pytest.raises(AuthFeil):
        les_token(f"{falsk}.{ekte_sig}", N)


def test_annan_nokkel_blir_avvist():
    with pytest.raises(AuthFeil):
        les_token(lag_token("ola", N), N2)


def test_utgaatt_token_blir_avvist():
    t = lag_token("ola", N, levetid=10, no=1000)
    assert les_token(t, N, no=1005) == "ola"
    with pytest.raises(AuthFeil):
        les_token(t, N, no=1011)


def test_soppel_blir_avvist():
    for daarleg in ["", "abc", "a.b.c", "....", None, 12345,
                    "eyJhbGciOiJub25lIn0.", "a." + "b" * 100]:
        with pytest.raises(AuthFeil):
            les_token(daarleg, N)


def test_signatur_utan_kropp_blir_avvist():
    with pytest.raises(AuthFeil):
        les_token("." + lag_token("ola", N).split(".")[1], N)


def test_feilmeldinga_avsloerer_ingenting():
    """Skil du mellom utgaatt og feil signatur, hjelper du angriparen."""
    utgaatt = lag_token("ola", N, levetid=1, no=1000)
    feil_sig = lag_token("ola", N2)
    a = b = ""
    try:
        les_token(utgaatt, N, no=99999)
    except AuthFeil as e:
        a = str(e)
    try:
        les_token(feil_sig, N)
    except AuthFeil as e:
        b = str(e)
    assert a == b, "Feilmeldingane skil mellom feiltypar"


def test_manglande_nokkel_stoppar_appen(monkeypatch):
    monkeypatch.delenv("VIDEOAPP_TOKEN_NOKKEL", raising=False)
    with pytest.raises(AuthFeil):
        hent_nokkel()


def test_for_kort_nokkel_blir_avvist():
    with pytest.raises(AuthFeil):
        hent_nokkel("kort")


def test_nokkel_frae_miljoeet(monkeypatch):
    monkeypatch.setenv("VIDEOAPP_TOKEN_NOKKEL", N)
    assert les_token(lag_token("ola")) == "ola"


def test_tom_brukar_blir_avvist():
    with pytest.raises(AuthFeil):
        lag_token("", N)
