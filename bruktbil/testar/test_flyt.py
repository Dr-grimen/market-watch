"""Heile handelen frå skiltnummer til utbetaling — og alle måtane han kan feile.

Testane går rett på `flyt`, ikkje via HTTP. Det er der reglane bur, og det er
der dei må halde.
"""

import unittest

from app import kontrakt
from app.modell import GEBYR_KRONER, Feil, Rolle, Steg
from app.tenester import bankid, betaling, eigarskifte
from app import flyt
from testar.hjelp import gyldig_fnr, gyldig_konto

SELJAR = Rolle.SELJAR.value
KJOPAR = Rolle.KJOPAR.value


def nytt_sal(pris=179000):
    return flyt.opprett_sal(
        skilt="DB12345",
        pris=pris,
        namn="Ola Nordmann",
        fnr=gyldig_fnr("01019"),
        telefon="90000000",
        epost="ola@example.no",
        adresse="Storgata 1, 5000 Bergen",
        kontonummer=gyldig_konto(),
    )


def signer(h, rolle):
    okt = flyt.start_signering(h, rolle)
    return flyt.fullfor_signering(h, rolle, kode=okt["kode"])


def heile_vegen(pris=179000):
    h = nytt_sal(pris)
    flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"), telefon="90000001", epost="kari@example.no")
    flyt.set_vilkaar(h, SELJAR, utstyr="To nøklar, sommardekk", kjende_feil="Ripe i lakken bak")
    flyt.send_til_signering(h, SELJAR)
    signer(h, SELJAR)
    signer(h, KJOPAR)
    flyt.opprett_betaling(h, KJOPAR)
    flyt.stadfest_betaling(h)
    flyt.send_salsmelding(h, SELJAR)
    flyt.stadfest_salsmelding(h, KJOPAR)
    return h


class Flyten(unittest.TestCase):
    def setUp(self):
        betaling.nullstill()
        eigarskifte.nullstill()

    def test_heile_handelen_gaar_gjennom(self):
        h = heile_vegen()
        self.assertEqual(h.steg, Steg.FULLFORT.value)
        self.assertEqual(h.betaling["status"], betaling.UTBETALT)
        self.assertEqual(h.eigarskifte["status"], eigarskifte.FULLFORT)
        self.assertTrue(h.begge_har_signert)

    def test_kjoparen_betaler_bil_pluss_omreg_pluss_gebyr(self):
        h = nytt_sal(179000)
        self.assertEqual(
            h.totalt_aa_betale, 179000 + h.omregistreringsavgift + GEBYR_KRONER
        )

    def test_seljaren_faar_kjopesummen_ikkje_gebyret(self):
        h = heile_vegen(200000)
        self.assertEqual(h.betaling["belop"], h.totalt_aa_betale)
        self.assertEqual(h.pris, 200000)
        self.assertEqual(h.betaling["gebyr"], GEBYR_KRONER)

    def test_pengane_staar_paa_klientkonto_til_eigarskiftet_er_gjort(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        signer(h, KJOPAR)
        flyt.opprett_betaling(h, KJOPAR)
        flyt.stadfest_betaling(h)
        self.assertEqual(h.betaling["status"], betaling.PAA_KLIENTKONTO)

        flyt.send_salsmelding(h, SELJAR)
        # Framleis ikkje utbetalt: kjøparen har ikkje stadfesta.
        self.assertEqual(h.betaling["status"], betaling.PAA_KLIENTKONTO)

        flyt.stadfest_salsmelding(h, KJOPAR)
        self.assertEqual(h.betaling["status"], betaling.UTBETALT)


class ReglarSomIkkjeKanOmgaaast(unittest.TestCase):
    def setUp(self):
        betaling.nullstill()
        eigarskifte.nullstill()

    def test_kan_ikkje_signere_foer_kjoparen_er_med(self):
        h = nytt_sal()
        with self.assertRaises(Feil):
            flyt.start_signering(h, SELJAR)

    def test_kan_ikkje_betale_foer_begge_har_signert(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        with self.assertRaises(Feil):
            flyt.opprett_betaling(h, KJOPAR)

    def test_kan_ikkje_melde_eigarskifte_foer_pengane_er_inne(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        signer(h, KJOPAR)
        flyt.opprett_betaling(h, KJOPAR)
        with self.assertRaises(Feil):
            flyt.send_salsmelding(h, SELJAR)

    def test_prisen_kan_ikkje_endrast_etter_signering(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        with self.assertRaises(Feil):
            flyt.set_vilkaar(h, SELJAR, pris=1)

    def test_feil_bankid_kode_signerer_ikkje(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        flyt.start_signering(h, SELJAR)
        with self.assertRaises(Feil):
            flyt.fullfor_signering(h, SELJAR, kode="000000")
        self.assertFalse(h.seljar.signert)

    def test_ugyldig_foedselsnummer_blir_stoppa(self):
        h = nytt_sal()
        with self.assertRaises(Feil):
            flyt.bli_med(h, namn="Kari Nordmann", fnr="12345678901")

    def test_kjoparen_kan_ikkje_setje_vilkaara(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        with self.assertRaises(Feil):
            flyt.set_vilkaar(h, KJOPAR, pris=1000)

    def test_seljaren_kan_ikkje_stadfeste_salsmeldinga_sjolv(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        signer(h, KJOPAR)
        flyt.opprett_betaling(h, KJOPAR)
        flyt.stadfest_betaling(h)
        flyt.send_salsmelding(h, SELJAR)
        with self.assertRaises(Feil):
            flyt.stadfest_salsmelding(h, SELJAR)

    def test_ugyldig_skilt_blir_avvist(self):
        with self.assertRaises(Feil):
            flyt.opprett_sal(skilt="bil123", pris=100, namn="Ola", fnr=gyldig_fnr())

    def test_ugyldig_kontonummer_blir_avvist(self):
        with self.assertRaises(Feil):
            flyt.opprett_sal(
                skilt="DB12345",
                pris=100000,
                namn="Ola",
                fnr=gyldig_fnr(),
                kontonummer="11111111111",
            )

    def test_avbrot_refunderer_kjoparen(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        signer(h, KJOPAR)
        flyt.opprett_betaling(h, KJOPAR)
        flyt.stadfest_betaling(h)
        flyt.avbryt(h, KJOPAR, "Bilen svarte ikkje til beskrivinga")
        self.assertEqual(h.steg, Steg.AVBROTEN.value)
        self.assertEqual(h.betaling["status"], betaling.REFUNDERT)

    def test_fullfoert_handel_kan_ikkje_avbrytast(self):
        h = heile_vegen()
        with self.assertRaises(Feil):
            flyt.avbryt(h, KJOPAR)


class Kontrakten(unittest.TestCase):
    def setUp(self):
        betaling.nullstill()
        eigarskifte.nullstill()

    def test_kontrakten_har_med_pris_skilt_og_partar(self):
        h = heile_vegen()
        t = kontrakt.tekst(h)
        self.assertIn("DB12345", t)
        self.assertIn("179 000 kr", t)
        self.assertIn("Ola Nordmann", t)
        self.assertIn("Kari Nordmann", t)
        self.assertIn("kjøpslova § 19", t)

    def test_foedselsnummer_staar_aldri_i_klartekst(self):
        fnr = gyldig_fnr("01019")
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        self.assertNotIn(fnr, kontrakt.tekst(h))
        self.assertNotIn(fnr, str(h.til_dict()))
        self.assertIn(fnr[:6] + "*****", kontrakt.tekst(h))

    def test_signaturgrunnlaget_endrar_seg_ikkje_naar_nokon_signerer(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        foer = kontrakt.fingeravtrykk(h)
        signer(h, SELJAR)
        self.assertEqual(foer, kontrakt.fingeravtrykk(h))

    def test_endra_kontrakt_blir_oppdaga(self):
        h = nytt_sal()
        flyt.bli_med(h, namn="Kari Nordmann", fnr=gyldig_fnr("02029"))
        flyt.set_vilkaar(h, SELJAR)
        flyt.send_til_signering(h, SELJAR)
        signer(h, SELJAR)
        signer(h, KJOPAR)
        self.assertTrue(kontrakt.er_urørt(h))
        h.pris = 1  # nokon har rota med rada i databasen
        self.assertFalse(kontrakt.er_urørt(h))
        with self.assertRaises(Feil):
            flyt.opprett_betaling(h, KJOPAR)


class Heftingar(unittest.TestCase):
    def test_pant_blir_vist_som_merknad_og_staar_i_kontrakten(self):
        h = flyt.opprett_sal(
            skilt="EL45678",
            pris=329000,
            namn="Kari",
            fnr=gyldig_fnr(),
            kontonummer=gyldig_konto(),
        )
        self.assertTrue(any("Heftelse" in m for m in h.bil["merknader"]))
        self.assertIn("Santander", kontrakt.tekst(h))


if __name__ == "__main__":
    unittest.main()
