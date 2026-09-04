"""Heile vegen frå «lag video» til ferdig fil.

Rekkjefølgja her er ikkje tilfeldig. Ho avgjer om folk blir trekte
kredittar for noko dei aldri fekk:

  1. Moderer FØRST. Blir innhaldet avvist, har vi ikkje trekt noko.
     Trekk-så-moderer gjer at avviste brukarar må ha pengane att, og
     refusjonar er både arbeid og eit dårleg omdøme.
  2. Reserver kredittar. No veit vi at jobben er lovleg å køyre.
  3. Forbetre prompten. Feilar dette, går vi vidare med brukaren sin
     eigen tekst - det skal aldri stoppe ein betalt video.
  4. Generer, med failover mellom leverandørar.
  5. Gjer opp ved suksess, FRIGI ved feil.

Steg 5 er det viktigaste. Kvar einaste utgang frå denne funksjonen må
anten gjere opp eller frigi reservasjonen. Går ein veg ut utan begge
delar, blir kredittane hengande, og brukaren har betalt for ingenting.
"""

import logging
import uuid
from dataclasses import dataclass

from .prompt import forbetre
from .providers.base import Jobb, VarigFeil
from .providers.router import IngenLeverandor

log = logging.getLogger(__name__)

# Utfall
OK = "ok"
AVVIST = "avvist"              # moderering sa nei - ingen kredittar trekte
FOR_LITE = "for_lite"          # tom saldo - ingen kredittar trekte
FEILA = "feila"                # vi klarte det ikkje - kredittar frigitte
USIKKER = "usikker"            # VI klarte ikkje sjekke. Vaar feil, ikkje deira.


@dataclass(frozen=True)
class Utfall:
    status: str
    video_url: str = ""
    grunn: str = ""
    leverandor: str = ""
    kredittar_trekte: int = 0
    prompt_brukt: str = ""

    @property
    def ok(self):
        return self.status == OK


class Verkstad:
    """Set saman moderering, ledger, promptforbetring og ruting."""

    def __init__(self, ledger, ruter, prisbok, moderering,
                 anthropic_nokkel=None):
        self.ledger = ledger
        self.ruter = ruter
        self.prisbok = prisbok
        self.moderering = moderering
        self.anthropic_nokkel = anthropic_nokkel

    def lag_video(self, brukar, bilde_url, onske, nivaa="standard",
                  bilde_b64=None, jobb_id=None):
        """Lag éin video. Returnerer alltid eit Utfall, kastar aldri.

        jobb_id er idempotensnøkkelen. Sender appen same jobben to
        gonger fordi nettet datt, blir brukaren trekt éin gong.
        """
        jobb_id = jobb_id or str(uuid.uuid4())
        n = self.prisbok.nivaa[nivaa]

        # 1. Moderering, før pengar er i spel.
        vurdering = self.moderering.sjekk(onske, bilde_b64=bilde_b64,
                                          brukar=brukar)
        if not vurdering.ok:
            # Skil mellom "innhaldet er avvist" og "vi klarte ikkje sjekke".
            # Det fyrste skal brukaren ikkje prove igjen; det andre skal
            # han prove igjen, og det er vi som har eit problem.
            return Utfall(
                status=USIKKER if vurdering.usikker else AVVIST,
                grunn=vurdering.grunn)

        # 2. Reserver. Feilar dette, er ingenting trekt.
        try:
            reservasjon = self.ledger.reserver(brukar, n.kredittar,
                                               idem=f"jobb:{jobb_id}")
        except Exception as e:                      # ForLiteSaldo m.m.
            log.info("Kunne ikkje reservere for %s: %s", brukar, e)
            return Utfall(status=FOR_LITE, grunn=str(e))

        # Frå og med her MÅ vi gjere opp eller frigi på kvar veg ut.
        try:
            # 3. Betre prompt. Feilar open - brukaren sin tekst er nok.
            prompt = forbetre(onske, api_nokkel=self.anthropic_nokkel)

            # 4. Generer.
            resultat = self.ruter.generer(
                Jobb(bilde_url=bilde_url, prompt=prompt,
                     sekund=n.sekund, boette=n.boette),
                nivaa)
        except VarigFeil as e:
            # Leverandøren avviste jobben. Brukaren skal ikkje betale
            # for noko han ikkje fekk, sjølv om det var hans eige bilde
            # som var problemet.
            self.ledger.frigi(reservasjon.id)
            log.info("Varig feil for %s: %s", brukar, e)
            return Utfall(status=AVVIST,
                          grunn="Vi klarte ikkje å lage video av dette biletet.")
        except IngenLeverandor as e:
            self.ledger.frigi(reservasjon.id)
            log.error("Ingen leverandør tilgjengeleg: %s", e)
            return Utfall(status=FEILA,
                          grunn="Tenesta er overbelasta. Prøv igjen om litt.")
        except Exception as e:                      # noqa: BLE001
            # Uventa feil skal aldri koste brukaren kredittar.
            self.ledger.frigi(reservasjon.id)
            log.exception("Uventa feil i jobb %s: %s", jobb_id, e)
            return Utfall(status=FEILA,
                          grunn="Noko gjekk gale. Kredittane er ikkje brukte.")

        # 5. Suksess.
        self.ledger.gjer_opp(reservasjon.id)
        return Utfall(status=OK, video_url=resultat.video_url,
                      leverandor=resultat.leverandor,
                      kredittar_trekte=n.kredittar, prompt_brukt=prompt)
