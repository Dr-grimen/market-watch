"""Same handel som i test_flyt, men gjennom HTTP — slik ein brukar gjer det.

Her testar vi det rutene har ansvar for: skjema inn, rett side ut, og at
lenkene faktisk stengjer folk ute frå handlar dei ikkje er part i.
"""

import os
import re
import tempfile
import unittest

os.environ["BRUKTBIL_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import lager  # noqa: E402
from app.web import app  # noqa: E402
from testar.hjelp import gyldig_fnr, gyldig_konto  # noqa: E402

KODE = re.compile(r'<div class="kode">\s*([A-Z0-9]{6})\s*</div>')


class Nettflyten(unittest.TestCase):
    def setUp(self):
        lager.klargjer()
        lager.slett_alt()
        self.k = TestClient(app, follow_redirects=True)

    def opprett(self):
        svar = self.k.post(
            "/nytt-sal",
            data={
                "skilt": "DB12345",
                "pris": "179000",
                "namn": "Ola Nordmann",
                "fnr": gyldig_fnr("01019"),
                "kontonummer": gyldig_konto(),
                "telefon": "90000000",
                "adresse": "Storgata 1, Bergen",
            },
        )
        self.assertEqual(svar.status_code, 200)
        return svar

    def test_framsida_svarar(self):
        svar = self.k.get("/")
        self.assertEqual(svar.status_code, 200)
        self.assertIn("Sel eller kjøp bruktbil", svar.text)

    def test_heile_handelen_gjennom_http(self):
        svar = self.opprett()
        self.assertIn("Volkswagen", svar.text)
        seljarlenke = str(svar.url.path)
        kode = KODE.search(svar.text).group(1)

        svar = self.k.post(
            "/bli-med",
            data={"kode": kode, "namn": "Kari Nordmann", "fnr": gyldig_fnr("02029")},
        )
        kjoparlenke = str(svar.url.path)
        self.assertIn("Volkswagen", svar.text)

        self.k.post(f"{seljarlenke}/vilkaar", data={"pris": "175000", "utstyr": "To nøklar"})
        self.k.post(f"{seljarlenke}/til-signering")

        for lenke in (seljarlenke, kjoparlenke):
            side = self.k.post(f"{lenke}/signer")
            bankidkode = re.search(r'class="kode">(\d{6})<', side.text).group(1)
            self.k.post(f"{lenke}/signer/stadfest", data={"kode": bankidkode})

        self.k.post(f"{kjoparlenke}/betal")
        self.k.post(f"{kjoparlenke}/betal/stadfest")
        self.k.post(f"{seljarlenke}/salsmelding")
        slutt = self.k.post(f"{kjoparlenke}/salsmelding/stadfest")

        self.assertIn("Fullført", slutt.text)
        self.assertIn("Kvittering", slutt.text)

        api = self.k.get("/api/handel" + seljarlenke[2:]).json()
        self.assertEqual(api["steg"], "fullfort")
        self.assertEqual(api["betaling"]["status"], "utbetalt")
        self.assertEqual(api["pris"], 175000)

    def test_feil_token_gir_ikkje_tilgang(self):
        svar = self.opprett()
        sti = str(svar.url.path).rsplit("/", 1)[0]
        nekta = self.k.get(f"{sti}/feil-token")
        self.assertEqual(nekta.status_code, 400)
        self.assertNotIn("Volkswagen", nekta.text)

    def test_seljaren_kjem_ikkje_inn_paa_kjoparlenka(self):
        svar = self.opprett()
        seljarlenke = str(svar.url.path)
        hid, _, token = seljarlenke.split("/")[2:5]
        blanda = self.k.get(f"/h/{hid}/kjopar/{token}")
        self.assertEqual(blanda.status_code, 400)

    def test_kontrakten_kan_lesast_av_begge(self):
        svar = self.opprett()
        seljarlenke = str(svar.url.path)
        kontrakt = self.k.get(f"{seljarlenke}/kontrakt")
        self.assertIn("KJØPEKONTRAKT", kontrakt.text)
        self.assertIn("DB12345", kontrakt.text)

    def test_ugyldig_skilt_gir_forstaaeleg_feil(self):
        svar = self.k.post(
            "/nytt-sal",
            data={"skilt": "hallo", "pris": "1000", "namn": "Ola", "fnr": gyldig_fnr()},
        )
        self.assertEqual(svar.status_code, 400)
        self.assertIn("skiltnummer", svar.text)

    def test_api_kjoretoy(self):
        d = self.k.get("/api/kjoretoy/el45678").json()
        self.assertEqual(d["merke"], "Tesla")
        self.assertTrue(d["merknader"])

    def test_helse(self):
        self.assertEqual(self.k.get("/helse").json()["status"], "oppe")


if __name__ == "__main__":
    unittest.main()
