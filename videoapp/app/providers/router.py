"""Ruteren. Billegast først, og aldri ned på grunn av éin leverandør.

To jobbar:

1. Vel billegaste aktive leverandør som klarer nivået. Rekkjefølgja
   kjem frå providers.yaml, ikkje frå kode.

2. Fell over ved mellombels feil. Brukaren skal aldri sjå ei feilmelding
   frå ein leverandør - berre at det tok litt lengre tid.

Straumbrytaren finst fordi det å prøve ein leverandør som er nede
kostar deg tid på KVAR jobb. Etter nok feil på rad hoppar vi over han
ei stund, og prøver forsiktig igjen etterpå.
"""

import logging
import time

from .base import MellombelsFeil, VarigFeil

log = logging.getLogger(__name__)

# Så mange feil på rad før vi hoppar over ein leverandør.
FEIL_FOR_BRYT = 5
# Kor lenge vi held han ute før vi prøver éin gong til.
KVILE_SEKUND = 60


class IngenLeverandor(Exception):
    """Alle kandidatane feila eller er utestengde."""


class Straumbrytar:
    """Held styr på kven som er nede, per leverandør."""

    def __init__(self, feil_for_bryt=FEIL_FOR_BRYT, kvile=KVILE_SEKUND):
        self.feil_for_bryt = feil_for_bryt
        self.kvile = kvile
        self._feil = {}
        self._ute_til = {}

    def open(self, nokkel):
        """Er denne leverandøren utestengd akkurat no?"""
        til = self._ute_til.get(nokkel, 0)
        if til and time.time() >= til:
            # Kvila er over. Slepp gjennom eitt forsøk.
            del self._ute_til[nokkel]
            self._feil[nokkel] = self.feil_for_bryt - 1
            return False
        return bool(til)

    def feila(self, nokkel):
        n = self._feil.get(nokkel, 0) + 1
        self._feil[nokkel] = n
        if n >= self.feil_for_bryt:
            self._ute_til[nokkel] = time.time() + self.kvile
            log.warning("Stenger ute %s i %ss etter %s feil", nokkel,
                        self.kvile, n)

    def lukkast(self, nokkel):
        self._feil.pop(nokkel, None)
        self._ute_til.pop(nokkel, None)


class Ruter:
    def __init__(self, prisbok, adaptere, straumbrytar=None):
        """adaptere: {leverandor_nokkel: Leverandor-instans}"""
        self.prisbok = prisbok
        self.adaptere = adaptere
        self.brytar = straumbrytar or Straumbrytar()

    def kandidatar(self, nivaa_nokkel, modus="bilde_til_video"):
        """Kven som kan ta jobben, billegast først, utestengde vekke."""
        ut = []
        for lev in self.prisbok.kandidatar(nivaa_nokkel, modus):
            adapter = self.adaptere.get(lev.nokkel)
            if adapter is None or not adapter.tilgjengeleg():
                continue
            if self.brytar.open(lev.nokkel):
                continue
            ut.append((lev, adapter))
        return ut

    def generer(self, jobb, nivaa_nokkel):
        """Prøv nedover lista til éin lukkast.

        Varig feil stoppar med ein gong - det hjelper ikkje å sende eit
        avvist bilde til fire leverandørar. Mellombels feil går vidare.
        """
        kand = self.kandidatar(nivaa_nokkel, jobb.modus)
        if not kand:
            raise IngenLeverandor(
                f"Ingen tilgjengeleg leverandør for {nivaa_nokkel!r}. "
                "Alle er anten utestengde, av, eller manglar API-nøkkel.")

        siste = None
        for lev, adapter in kand:
            adapter._nok_per_usd = self.prisbok.nok_per_usd
            try:
                resultat = adapter.generer(jobb)
                self.brytar.lukkast(lev.nokkel)
                return resultat
            except VarigFeil:
                # Jobben er problemet, ikkje leverandøren. Ikkje tel
                # dette mot straumbrytaren, og ikkje prøv dei andre.
                raise
            except MellombelsFeil as e:
                log.warning("Leverandør %s feila mellombels: %s", lev.nokkel, e)
                self.brytar.feila(lev.nokkel)
                siste = e

        raise IngenLeverandor(
            f"Alle {len(kand)} leverandørane feila. Siste: {siste}")
