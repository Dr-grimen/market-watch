"""Bestilling og køyring, delt i to.

Den synkrone Verkstad passar for eit skript. For ein app med kø må
jobben delast, fordi dei to halvdelane har heilt ulik hastigheit:

  BESTILLING (raskt, brukaren ventar på svar)
    moderer -> reserver kredittar -> legg i kø
    Brukaren får med ein gong vite om han blei avvist eller er tom for
    kredittar. Det er dei to svara han treng no.

  KOEYRING (tregt, ein arbeidar tek det)
    hent frå kø -> forbetre prompt -> generer -> gjer opp eller frigi
    Tek eit minutt eller ti. Brukaren får push når det er klart.

Reservasjonen blir gjord ved BESTILLING, ikkje ved køyring. Det er med
vilje: elles kunne ein brukar leggje hundre jobbar i kø med saldo til
ti, og nittien av dei ville feilast heilt til slutt etter å ha teke
plass i køen heile vegen.

Den viktigaste regelen i heile fila: EIN JOBB SOM GIR OPP MAA FRIGI
KREDITTANE. Gjer han ikkje det, har brukaren betalt for ingenting, og
det er den feilen som gir deg eitt-stjerners omtalar.
"""

import logging

from . import ko as ko_modul
from .jobb import AVVIST, FEILA, FOR_LITE, OK, Utfall
from .prompt import forbetre
from .providers.base import Jobb, VarigFeil
from .providers.router import IngenLeverandor

log = logging.getLogger(__name__)


class Bestilling:
    """Tek imot ei tinging. Rask - brukaren ventar på dette svaret."""

    def __init__(self, ko, ledger, prisbok, moderering):
        self.ko = ko
        self.ledger = ledger
        self.prisbok = prisbok
        self.moderering = moderering

    def bestill(self, brukar, bilde_url, onske, nivaa="standard",
                bilde_b64=None, idem=None):
        """Returnerer (jobb_id, Utfall). jobb_id er None om det ikkje gjekk."""
        n = self.prisbok.nivaa[nivaa]

        vurdering = self.moderering.sjekk(onske, bilde_b64=bilde_b64,
                                          brukar=brukar)
        if not vurdering.ok:
            return None, Utfall(status=AVVIST, grunn=vurdering.grunn)

        jobb_id = self.ko.legg_til(brukar, bilde_url, onske, nivaa, idem=idem)

        # Er jobben alt reservert, er dette eit gjentak. Ikkje trekk igjen.
        rad = self.ko.status(jobb_id)
        if rad.get("reservasjon_id"):
            return jobb_id, Utfall(status=OK, grunn="Alt i kø")

        try:
            res = self.ledger.reserver(brukar, n.kredittar,
                                       idem=f"jobb:{jobb_id}")
        except Exception as e:
            # Ingen kredittar. Ta jobben ut av køen igjen - elles ligg
            # han der og blir plukka opp av ein arbeidar som ikkje har
            # nokon reservasjon å gjere opp.
            self.ko.feila(jobb_id, "for lite kredittar", kan_prove_igjen=False)
            return None, Utfall(status=FOR_LITE, grunn=str(e))

        self.ko.knyt_reservasjon(jobb_id, res.id)
        return jobb_id, Utfall(status=OK, grunn="I kø")


class Arbeidar:
    """Køyrer jobbar frå køen. Treg - ingen ventar direkte på denne."""

    def __init__(self, ko, ledger, ruter, prisbok, namn="arbeidar-1",
                 anthropic_nokkel=None):
        self.ko = ko
        self.ledger = ledger
        self.ruter = ruter
        self.prisbok = prisbok
        self.namn = namn
        self.anthropic_nokkel = anthropic_nokkel

    def koyr_ein(self):
        """Tek éin jobb. Returnerer Utfall, eller None om køen er tom."""
        rad = self.ko.hent(self.namn)
        if rad is None:
            return None

        jobb_id = rad["id"]
        res_id = rad["reservasjon_id"]
        n = self.prisbok.nivaa[rad["nivaa"]]

        try:
            prompt = forbetre(rad["onske"], api_nokkel=self.anthropic_nokkel)
            resultat = self.ruter.generer(
                Jobb(bilde_url=rad["bilde_url"], prompt=prompt,
                     sekund=n.sekund, boette=n.boette),
                rad["nivaa"])
        except VarigFeil as e:
            # Jobben er umogleg. Å prøve igjen hjelper ikkje.
            self._gi_opp(jobb_id, res_id, str(e))
            return Utfall(status=AVVIST,
                          grunn="Vi klarte ikkje å lage video av dette biletet.")
        except (IngenLeverandor, Exception) as e:   # noqa: BLE001
            # Mellombels. Køen avgjer om det er fleire forsøk att.
            if self.ko.feila(jobb_id, str(e)):
                log.info("Jobb %s prøver igjen: %s", jobb_id, e)
                return Utfall(status=FEILA, grunn="Prøver igjen")
            self._frigi(res_id, jobb_id)
            return Utfall(status=FEILA,
                          grunn="Vi klarte det ikkje. Kredittane er ikkje brukte.")

        self.ko.fullfor(jobb_id, resultat.video_url)
        if res_id:
            self.ledger.gjer_opp(res_id)
        return Utfall(status=OK, video_url=resultat.video_url,
                      leverandor=resultat.leverandor,
                      kredittar_trekte=n.kredittar, prompt_brukt=prompt)

    def koyr_til_tom(self, maks=100):
        """Køyr til køen er tom. Returnerer talet på jobbar som blei tekne."""
        n = 0
        while n < maks and self.koyr_ein() is not None:
            n += 1
        return n

    def _gi_opp(self, jobb_id, res_id, grunn):
        self.ko.feila(jobb_id, grunn, kan_prove_igjen=False)
        self._frigi(res_id, jobb_id)

    def _frigi(self, res_id, jobb_id):
        if not res_id:
            log.error("Jobb %s gav opp utan reservasjon å frigi", jobb_id)
            return
        self.ledger.frigi(res_id)
