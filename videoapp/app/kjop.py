"""Apple-kjøp. Her er det ekte pengar, så her tek vi ingen snarvegar.

StoreKit 2 sender ein signert transaksjon (JWS) frå appen til deg. Det
freistande - og feil - er å dekode han og lese produkt-id-en. Alle kan
lage ein JWS. Berre Apple kan signere ein.

Fire ting må stemme før vi gir kredittar. Sløyfar du éin, gir du bort
videoar:

1. SIGNATUREN. Sertifikatkjeda i JWS-hovudet må gå heilt opp til Apple
   sitt rotsertifikat, som vi har lagra sjølve. Utan denne kan kven som
   helst signere sin eigen "kvittering".

2. BUNDLE-ID. Kvitteringa må gjelde VÅR app. Ei ekte, gyldig signert
   Apple-kvittering frå ein heilt annan app er framleis ekte - ho er
   berre ikkje vår. Utan denne sjekken kan nokon kjøpe noko billeg i
   ein tilfeldig app og veksle det inn hos oss.

3. PRODUKT-ID. Må stå i lista vår. Kjøper nokon noko vi ikkje kjenner,
   er det ein feil - ikkje noko vi skal gjette kredittar for.

4. TRANSAKSJONS-ID SOM IDEMPOTENSNØKKEL. Apple sender same kvittering
   fleire gonger, og ein brukar kan sende henne om att sjølv. Ledgeren
   dedupliserer på denne, så same kjøp kan berre bli kredittar éin gong.

MERK: Apple sitt rotsertifikat følgjer ikkje med i repoet. Last det ned
frå https://www.apple.com/certificateauthority/ og legg det der
`apple_rot_sertifikat` peikar. Manglar det, nektar vi alle kjøp - vi
gjettar ikkje.
"""

import base64
import datetime
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import (
    encode_dss_signature)

log = logging.getLogger(__name__)

PRODUKSJON = "Production"
SANDKASSE = "Sandbox"


class KjopFeil(Exception):
    """Kvitteringa er ikkje god nok. Ingen kredittar."""


@dataclass(frozen=True)
class Kjop:
    transaksjon_id: str
    produkt_id: str
    bundle_id: str
    miljo: str
    kredittar: int

    @property
    def idem(self):
        """Nøkkelen ledgeren dedupliserer på. Eitt kjøp, éin gong."""
        return f"apple:{self.transaksjon_id}"


def _av_b64url(tekst):
    pad = "=" * (-len(tekst) % 4)
    return base64.urlsafe_b64decode(tekst + pad)


def _raa_til_der(sig):
    """ES256-signaturen i JWS er r||s. cryptography vil ha DER."""
    if len(sig) != 64:
        raise KjopFeil(f"Uventa signaturlengd: {len(sig)}")
    r = int.from_bytes(sig[:32], "big")
    s = int.from_bytes(sig[32:], "big")
    return encode_dss_signature(r, s)


def _sjekk_signatur(sertifikat, data, signatur):
    """Signerte dette sertifikatet desse dataa?"""
    nokkel = sertifikat.public_key()
    if isinstance(nokkel, ec.EllipticCurvePublicKey):
        nokkel.verify(_raa_til_der(signatur), data,
                      ec.ECDSA(hashes.SHA256()))
    elif isinstance(nokkel, rsa.RSAPublicKey):
        nokkel.verify(signatur, data, padding.PKCS1v15(), hashes.SHA256())
    else:
        raise KjopFeil(f"Ukjend nøkkeltype: {type(nokkel).__name__}")


def _sjekk_kjede(sertifikat, utferdar):
    """Signerte utferdaren dette sertifikatet?"""
    nokkel = utferdar.public_key()
    try:
        if isinstance(nokkel, ec.EllipticCurvePublicKey):
            nokkel.verify(sertifikat.signature,
                          sertifikat.tbs_certificate_bytes,
                          ec.ECDSA(sertifikat.signature_hash_algorithm))
        else:
            nokkel.verify(sertifikat.signature,
                          sertifikat.tbs_certificate_bytes,
                          padding.PKCS1v15(),
                          sertifikat.signature_hash_algorithm)
    except InvalidSignature:
        raise KjopFeil("Sertifikatkjeda heng ikkje saman") from None


def les_rot(sti):
    raa = Path(sti).read_bytes()
    try:
        return x509.load_der_x509_certificate(raa)
    except ValueError:
        return x509.load_pem_x509_certificate(raa)


class Kjopssjekk:
    def __init__(self, prisbok, rot_sti=None, bundle_id=None,
                 produkt=None, godta_sandkasse=None):
        k = prisbok._raw.get("kjop") or {}
        self.bundle_id = bundle_id or k.get("bundle_id", "")
        self.produkt = produkt if produkt is not None else dict(
            k.get("produkt") or {})
        self.godta_sandkasse = (k.get("godta_sandkasse", False)
                                if godta_sandkasse is None else godta_sandkasse)
        sti = rot_sti or k.get("apple_rot_sertifikat", "")

        if not self.bundle_id:
            raise KjopFeil("bundle_id manglar i konfigurasjonen")
        if not self.produkt:
            raise KjopFeil("Ingen produkt er definerte")

        self.rot = None
        if sti and Path(sti).exists():
            self.rot = les_rot(sti)
        else:
            # Ikkje kast her - appen skal kunne starte og servere alt
            # anna. Men kvart einaste kjøp blir avvist til dette er på
            # plass, og det skal seiast tydeleg.
            log.error(
                "Apple-rotsertifikatet manglar (%s). ALLE kjøp blir avviste. "
                "Last det ned frå apple.com/certificateauthority/", sti or "ikkje sett")

    def klar(self):
        return self.rot is not None

    def verifiser(self, jws, no=None):
        """Returnerer eit Kjop, eller kastar KjopFeil. Gjettar aldri."""
        if not self.klar():
            raise KjopFeil(
                "Kan ikkje stadfeste kjøp - Apple-rotsertifikatet manglar.")
        if not jws or not isinstance(jws, str):
            raise KjopFeil("Tom kvittering")

        bitar = jws.split(".")
        if len(bitar) != 3:
            raise KjopFeil("Kvitteringa er ikkje ein JWS")
        hovud_b64, kropp_b64, sig_b64 = bitar

        try:
            hovud = json.loads(_av_b64url(hovud_b64))
            signatur = _av_b64url(sig_b64)
        except Exception:
            raise KjopFeil("Kvitteringa kan ikkje lesast") from None

        if hovud.get("alg") != "ES256":
            # alg frå kvitteringa styrer ikkje kva vi gjer. Apple brukar
            # ES256; alt anna er eit forsøk på noko.
            raise KjopFeil(f"Uventa algoritme: {hovud.get('alg')}")

        kjede_raa = hovud.get("x5c") or []
        if len(kjede_raa) < 2:
            raise KjopFeil("Sertifikatkjeda manglar")

        try:
            kjede = [x509.load_der_x509_certificate(base64.b64decode(c))
                     for c in kjede_raa]
        except Exception:
            raise KjopFeil("Sertifikata kan ikkje lesast") from None

        no = time.time() if no is None else no
        self._sjekk_kjede_heilt_opp(kjede, no)

        # Signaturen over sjølve kvitteringa, med lauvsertifikatet.
        try:
            _sjekk_signatur(kjede[0], f"{hovud_b64}.{kropp_b64}".encode("ascii"),
                            signatur)
        except InvalidSignature:
            raise KjopFeil("Signaturen stemmer ikkje") from None

        try:
            kropp = json.loads(_av_b64url(kropp_b64))
        except Exception:
            raise KjopFeil("Innhaldet kan ikkje lesast") from None

        return self._les_kropp(kropp)

    def _sjekk_kjede_heilt_opp(self, kjede, no):
        for s in kjede:
            # not_valid_before/after er NAIVE datetime i UTC. .timestamp()
            # paa ein naiv datetime tolkar han som LOKAL tid, og da blir
            # gyldigheitssjekken feil med heile tidssoneforskjellen paa
            # ein server som ikkje koeyrer UTC. Tving UTC.
            gyldig_frae = s.not_valid_before.replace(
                tzinfo=datetime.timezone.utc).timestamp()
            gyldig_til = s.not_valid_after.replace(
                tzinfo=datetime.timezone.utc).timestamp()
            if not gyldig_frae <= no <= gyldig_til:
                raise KjopFeil("Eit sertifikat i kjeda er utgått")

        for i in range(len(kjede) - 1):
            _sjekk_kjede(kjede[i], kjede[i + 1])

        # Toppen av kjeda må vere VÅRT lagra Apple-rotsertifikat.
        # Utan denne samanlikninga kan kven som helst levere si eiga
        # sjølvsignerte kjede og bli trudd.
        if kjede[-1].fingerprint(hashes.SHA256()) != \
                self.rot.fingerprint(hashes.SHA256()):
            raise KjopFeil("Kjeda endar ikkje i Apple sitt rotsertifikat")

    def _les_kropp(self, kropp):
        bundle = kropp.get("bundleId", "")
        if bundle != self.bundle_id:
            # Ekte kvittering, feil app.
            log.warning("Kvittering for framand app: %s", bundle)
            raise KjopFeil("Kvitteringa gjeld ein annan app")

        miljo = kropp.get("environment", PRODUKSJON)
        if miljo == SANDKASSE and not self.godta_sandkasse:
            raise KjopFeil("Sandkassekvitteringar er ikkje godtekne her")

        produkt = kropp.get("productId", "")
        if produkt not in self.produkt:
            raise KjopFeil(f"Ukjent produkt: {produkt}")

        tid = kropp.get("transactionId", "")
        if not tid:
            raise KjopFeil("Kvitteringa manglar transactionId")

        return Kjop(transaksjon_id=str(tid), produkt_id=produkt,
                    bundle_id=bundle, miljo=miljo,
                    kredittar=int(self.produkt[produkt]))

    def losn_inn(self, ledger, brukar, jws, no=None):
        """Stadfest og gi kredittar. Same kvittering to gonger = éin gong."""
        kjop = self.verifiser(jws, no=no)
        ledger.kjop(brukar, kjop.kredittar, idem=kjop.idem)
        log.info("Kjøp %s: %s kredittar til %s", kjop.transaksjon_id,
                 kjop.kredittar, brukar)
        return kjop
