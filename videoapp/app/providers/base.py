"""Felles form for alle videoleverandørar.

Poenget med dette laget: appen skal aldri vite kven som lagar videoen.
Byttar du leverandør, byttar du ei linje i providers.yaml - ikkje kode.
"""

from dataclasses import dataclass


class LeverandorFeil(Exception):
    """Basis for alt som kan gå gale hos ein leverandør."""


class MellombelsFeil(LeverandorFeil):
    """Prøv ein annan leverandør. Timeout, 5xx, kø full, rate limit."""


class VarigFeil(LeverandorFeil):
    """Ikkje prøv på nytt. Ugyldig bilde, avvist av moderering, dårleg prompt.

    Skilnaden er viktig: mellombels feil skal falle over til neste
    leverandør, varig feil skal stoppe med ein gong. Behandlar du alt
    som mellombels, brenner du pengar på å prøve same umoglege jobben
    hos fire leverandørar.
    """


@dataclass(frozen=True)
class Jobb:
    """Det appen ber om, uavhengig av kven som skal gjere det."""
    bilde_url: str
    prompt: str
    sekund: int
    boette: str          # lav / medium / hd
    modus: str = "bilde_til_video"


@dataclass(frozen=True)
class Resultat:
    video_url: str
    leverandor: str
    sekund: int
    kostnad_nok: float


class Leverandor:
    """Arv denne for kvar ny leverandør. Tre metodar, ikkje meir."""

    nokkel = "abstrakt"

    def __init__(self, konfig, api_nokkel=None):
        self.konfig = konfig
        self.api_nokkel = api_nokkel

    def generer(self, jobb):
        """Send jobben. Returner Resultat, eller kast Mellombels/VarigFeil."""
        raise NotImplementedError

    def tilgjengeleg(self):
        """Har vi det som trengst for å bruke denne? Som regel: ein nøkkel."""
        return bool(self.api_nokkel)
