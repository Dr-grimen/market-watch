"""Testar for Apple-kjoep. Alle er forsoek paa aa faa gratis kredittar.

Vi lagar vaar eiga sertifikatkjede og signerer vaare eigne kvitteringar.
Det er einaste maaten aa teste dette utan ekte Apple-kvitteringar - og
det speglar noeyaktig kva ein angripar ville gjort.
"""

import base64
import datetime as dt
import json
import sys
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.kjop import Kjop, KjopFeil, Kjopssjekk
from app.ledger import Ledger
from app.pricing import Prisbok

BUNDLE = "no.sondre.videoapp"
PRODUKT = {"no.sondre.videoapp.kredittar250": 250}


def _nokkel():
    return ec.generate_private_key(ec.SECP256R1())


def _sert(namn, nokkel, utferdar_namn=None, utferdar_nokkel=None,
          dagar_frae=-1, dagar_til=365):
    no = dt.datetime.now(dt.timezone.utc)
    emne = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, namn)])
    b = (x509.CertificateBuilder()
         .subject_name(emne)
         .issuer_name(x509.Name([x509.NameAttribute(
             NameOID.COMMON_NAME, utferdar_namn or namn)]))
         .public_key(nokkel.public_key())
         .serial_number(x509.random_serial_number())
         .not_valid_before(no + dt.timedelta(days=dagar_frae))
         .not_valid_after(no + dt.timedelta(days=dagar_til)))
    return b.sign(utferdar_nokkel or nokkel, hashes.SHA256())


class Kjede:
    """Ei komplett kjede: rot -> mellom -> lauv, og ein signerar."""

    def __init__(self, lauv_dagar_til=365):
        self.rot_n = _nokkel()
        self.rot = _sert("Test Root", self.rot_n)
        self.mellom_n = _nokkel()
        self.mellom = _sert("Test Intermediate", self.mellom_n,
                            "Test Root", self.rot_n)
        self.lauv_n = _nokkel()
        self.lauv = _sert("Test Leaf", self.lauv_n, "Test Intermediate",
                          self.mellom_n, dagar_til=lauv_dagar_til)

    def rot_fil(self, tmp_path, namn="rot.der"):
        p = tmp_path / namn
        p.write_bytes(self.rot.public_bytes(serialization.Encoding.DER))
        return str(p)

    def jws(self, kropp, alg="ES256", tukle=False):
        def b64(raa):
            return base64.urlsafe_b64encode(raa).rstrip(b"=").decode()

        x5c = [base64.b64encode(s.public_bytes(serialization.Encoding.DER)).decode()
               for s in (self.lauv, self.mellom, self.rot)]
        h = b64(json.dumps({"alg": alg, "x5c": x5c}).encode())
        k = b64(json.dumps(kropp).encode())
        sig = self.lauv_n.sign(f"{h}.{k}".encode(), ec.ECDSA(hashes.SHA256()))

        # JWS vil ha raa r||s, ikkje DER
        from cryptography.hazmat.primitives.asymmetric.utils import (
            decode_dss_signature)
        r, s = decode_dss_signature(sig)
        raa = r.to_bytes(32, "big") + s.to_bytes(32, "big")

        if tukle:
            k = b64(json.dumps(dict(kropp, productId="juks")).encode())
        return f"{h}.{k}.{b64(raa)}"


def kropp(**kw):
    d = {"bundleId": BUNDLE, "productId": "no.sondre.videoapp.kredittar250",
         "transactionId": "2000000123", "environment": "Production"}
    d.update(kw)
    return d


@pytest.fixture
def rigg(tmp_path):
    kjede = Kjede()

    def bygg(k=None, **kw):
        k = k or kjede
        return Kjopssjekk(Prisbok(), rot_sti=k.rot_fil(tmp_path, f"r{id(k)}.der"),
                          bundle_id=BUNDLE, produkt=dict(PRODUKT), **kw)

    return kjede, bygg


# -- det som skal gaa gjennom -----------------------------------------

def test_ekte_kvittering_blir_godteken(rigg):
    kjede, bygg = rigg
    k = bygg().verifiser(kjede.jws(kropp()))
    assert k.kredittar == 250
    assert k.transaksjon_id == "2000000123"
    assert k.idem == "apple:2000000123"


def test_innloesing_gir_kredittar(rigg):
    kjede, bygg = rigg
    lg = Ledger(":memory:")
    bygg().losn_inn(lg, "ola", kjede.jws(kropp()))
    assert lg.saldo("ola") == 250
    lg.close()


def test_same_kvittering_to_gonger_gir_kredittar_ein_gong(rigg):
    """Apple sender om att, og brukaren kan sende om att sjolv."""
    kjede, bygg = rigg
    lg = Ledger(":memory:")
    jws = kjede.jws(kropp())
    s = bygg()
    s.losn_inn(lg, "ola", jws)
    s.losn_inn(lg, "ola", jws)
    assert lg.saldo("ola") == 250
    assert lg.stemmer()
    lg.close()


# -- angrepa ---------------------------------------------------------

def test_framand_kjede_blir_avvist(rigg):
    """Angriparen signerer si eiga kvittering med si eiga kjede."""
    _, bygg = rigg
    angripar = Kjede()
    with pytest.raises(KjopFeil, match="rotsertifikat"):
        bygg().verifiser(angripar.jws(kropp()))


def test_tuklaa_innhald_blir_avvist(rigg):
    """Ekte signatur, bytta produkt-id etterpaa."""
    kjede, bygg = rigg
    with pytest.raises(KjopFeil, match="[Ss]ignatur"):
        bygg().verifiser(kjede.jws(kropp(), tukle=True))


def test_kvittering_frae_annan_app_blir_avvist(rigg):
    """AEgte Apple-kvittering, men frae ein heilt annan app."""
    kjede, bygg = rigg
    with pytest.raises(KjopFeil, match="annan app"):
        bygg().verifiser(kjede.jws(kropp(bundleId="com.nokon.heilt.anna")))


def test_ukjent_produkt_blir_avvist(rigg):
    kjede, bygg = rigg
    with pytest.raises(KjopFeil, match="Ukjent produkt"):
        bygg().verifiser(kjede.jws(kropp(productId="noko.vi.ikkje.sel")))


def test_utgaatt_sertifikat_blir_avvist(rigg, tmp_path):
    """Gyldig kjede, gyldig signatur - men lauvet gjekk ut i gaar."""
    _, bygg = rigg
    gammal = Kjede(lauv_dagar_til=-1)
    s = Kjopssjekk(Prisbok(), rot_sti=gammal.rot_fil(tmp_path, "gammal.der"),
                   bundle_id=BUNDLE, produkt=dict(PRODUKT))
    with pytest.raises(KjopFeil, match="utgått"):
        s.verifiser(gammal.jws(kropp()))


def test_gyldigheit_blir_lesen_som_utc(rigg):
    """Sertifikatdatoane er naive i UTC.

    Les vi dei som lokal tid, blir sjekken feil med heile
    tidssoneforskjellen paa ein server som ikkje koeyrer UTC.
    """
    import datetime as _dt
    kjede, bygg = rigg
    lauv = kjede.lauv
    venta = lauv.not_valid_after.replace(tzinfo=_dt.timezone.utc).timestamp()
    # Rett etter utloep skal han avvisast, uansett kva sone serveren har.
    with pytest.raises(KjopFeil, match="utgått"):
        bygg().verifiser(kjede.jws(kropp()), no=venta + 60)


def test_sandkasse_blir_avvist_i_produksjon(rigg):
    kjede, bygg = rigg
    with pytest.raises(KjopFeil, match="[Ss]andkasse"):
        bygg(godta_sandkasse=False).verifiser(
            kjede.jws(kropp(environment="Sandbox")))


def test_sandkasse_gaar_naar_han_er_paa(rigg):
    kjede, bygg = rigg
    k = bygg(godta_sandkasse=True).verifiser(
        kjede.jws(kropp(environment="Sandbox")))
    assert k.miljo == "Sandbox"


def test_annan_algoritme_blir_avvist(rigg):
    """alg frae kvitteringa styrer ikkje kva vi gjer."""
    kjede, bygg = rigg
    with pytest.raises(KjopFeil, match="algoritme"):
        bygg().verifiser(kjede.jws(kropp(), alg="none"))


def test_soppel_blir_avvist(rigg):
    _, bygg = rigg
    s = bygg()
    for d in ["", "a.b", "a.b.c", None, "...", "x" * 200]:
        with pytest.raises(KjopFeil):
            s.verifiser(d)


def test_manglande_transaksjonsid_blir_avvist(rigg):
    kjede, bygg = rigg
    with pytest.raises(KjopFeil, match="transactionId"):
        bygg().verifiser(kjede.jws(kropp(transactionId="")))


def test_utan_rotsertifikat_blir_alt_avvist(rigg):
    """Feilar lukka. Manglar sertifikatet, gir vi ingen kredittar."""
    kjede, _ = rigg
    s = Kjopssjekk(Prisbok(), rot_sti="finst/ikkje.der", bundle_id=BUNDLE,
                   produkt=dict(PRODUKT))
    assert s.klar() is False
    with pytest.raises(KjopFeil, match="rotsertifikatet manglar"):
        s.verifiser(kjede.jws(kropp()))
