"""Kva ein video kostar deg, og kva han gir deg att.

All prising kjem frå config/providers.yaml. Ingen tal er hardkoda her.
Poenget er at du kan svare på "tener vi pengar på HD-nivået?" utan å
lese kode - og at eit build feilar viss svaret blir nei.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "providers.yaml"


class KonfigFeil(Exception):
    """Konfigurasjonen gir ikkje meining. Betre å stoppe enn å gjette."""


@dataclass(frozen=True)
class Leverandor:
    nokkel: str
    visingsnamn: str
    usd_per_second: float
    stottar: tuple
    maks_sekund: int
    opplosningar: dict          # boette -> leverandoren sin eigen streng
    region: str
    aktiv: bool

    def kostnad_nok(self, sekund, nok_per_usd):
        """Rå innkjøpspris for éin generering på dette talet sekund."""
        return self.usd_per_second * sekund * nok_per_usd

    def kan_levere(self, sekund, boette, modus):
        return (
            self.aktiv
            and modus in self.stottar
            and sekund <= self.maks_sekund
            and boette in self.opplosningar
        )

    def api_opplosning(self, boette):
        """Kva denne leverandøren sjølv kallar boetta. Går rett i API-kallet."""
        return self.opplosningar[boette]


@dataclass(frozen=True)
class Nivaa:
    nokkel: str
    visingsnamn: str
    sekund: int
    boette: str
    kredittar: int
    tving_billegast: bool


@dataclass(frozen=True)
class Marginrapport:
    """Svaret på 'tener vi pengar på dette nivået?'"""
    nivaa: str
    leverandor: str
    inntekt_brutto: float
    app_store_kutt: float
    gpu_kostnad: float
    faste_kostnader: float

    @property
    def inntekt_netto(self):
        return self.inntekt_brutto - self.app_store_kutt

    @property
    def kostnad_sum(self):
        return self.gpu_kostnad + self.faste_kostnader

    @property
    def bruttofortenest(self):
        return self.inntekt_netto - self.kostnad_sum

    @property
    def margin(self):
        """Brutto margin som brøkdel av netto inntekt. Kan vere negativ."""
        if self.inntekt_netto <= 0:
            return -1.0
        return self.bruttofortenest / self.inntekt_netto


class Prisbok:
    """Lastar konfigurasjonen og svarar på pris- og marginspørsmål."""

    def __init__(self, sti=None):
        raw = yaml.safe_load(Path(sti or CONFIG_PATH).read_text(encoding="utf-8"))
        self._raw = raw

        self.nok_per_usd = float(raw["valuta"]["nok_per_usd"])

        ok = raw["okonomi"]
        self.nok_per_kreditt = float(ok["nok_per_kreditt"])
        self.app_store_kutt = float(ok["app_store_kutt"])
        self.faste_kroner_per_video = float(ok["faste_kroner_per_video"])
        self.minste_margin = float(ok["minste_margin"])

        self.gave_ved_registrering = int(raw["gaver"]["ved_registrering"])

        ab = raw.get("abonnement") or {}
        self.abo_pris = float(ab.get("pris_nok", 0))
        self.abo_kredittar = int(ab.get("kredittar", 0))
        self.abo_venta_bruk = float(ab.get("venta_bruk", 0.6))
        self.abo_minste_margin_verstefall = float(
            ab.get("minste_margin_verstefall", 0.0))
        self.regenerering_kostar = bool(
            ab.get("regenerering_kostar_kredittar", True))

        self.leverandorar = {}
        for nokkel, d in raw["leverandorar"].items():
            self.leverandorar[nokkel] = Leverandor(
                nokkel=nokkel,
                visingsnamn=d["visingsnamn"],
                usd_per_second=float(d["usd_per_second"]),
                stottar=tuple(d["stottar"]),
                maks_sekund=int(d["maks_sekund"]),
                opplosningar=dict(d["opplosningar"]),
                region=d.get("region", "ukjend"),
                # Alt er på med mindre det uttrykkeleg er slått av.
                aktiv=bool(d.get("aktiv", True)),
            )

        self.nivaa = {}
        for nokkel, d in raw["nivaa"].items():
            self.nivaa[nokkel] = Nivaa(
                nokkel=nokkel,
                visingsnamn=d["visingsnamn"],
                sekund=int(d["sekund"]),
                boette=d["opplosning"],
                kredittar=int(d["kredittar"]),
                tving_billegast=bool(d.get("tving_billegast", False)),
            )

        if not any(lev.aktiv for lev in self.leverandorar.values()):
            raise KonfigFeil("Ingen aktive leverandørar. Appen kan ikkje levere noko.")

    def kandidatar(self, nivaa_nokkel, modus="bilde_til_video"):
        """Aktive leverandørar som klarer dette nivået, billegast først.

        Rekkjefølgja her ER prispolitikken. Ruteren tek berre første
        som svarar, og fell vidare nedover ved feil.
        """
        n = self._nivaa(nivaa_nokkel)
        passar = [
            lev for lev in self.leverandorar.values()
            if lev.kan_levere(n.sekund, n.boette, modus)
        ]
        return sorted(passar, key=lambda lev: (lev.usd_per_second, lev.nokkel))

    def billegaste(self, nivaa_nokkel, modus="bilde_til_video"):
        kand = self.kandidatar(nivaa_nokkel, modus)
        if not kand:
            raise KonfigFeil(
                f"Ingen aktiv leverandør klarer nivået {nivaa_nokkel!r} ({modus}). "
                "Sjekk maks_sekund og opplosningar i providers.yaml."
            )
        return kand[0]

    def kostnad(self, nivaa_nokkel, leverandor_nokkel):
        """Rå GPU-kostnad i kroner for éin generering."""
        n = self._nivaa(nivaa_nokkel)
        lev = self.leverandorar[leverandor_nokkel]
        return lev.kostnad_nok(n.sekund, self.nok_per_usd)

    def margin(self, nivaa_nokkel, leverandor_nokkel=None, forsok=1.0):
        """Marginrapport for eitt nivå.

        forsok er kor mange genereringar det i snitt går med per levert
        video. Regenererer folk mykje, stig kostnaden proporsjonalt -
        difor er dette ein parameter og ikkje ein konstant.
        """
        n = self._nivaa(nivaa_nokkel)
        lev = (
            self.leverandorar[leverandor_nokkel]
            if leverandor_nokkel
            else self.billegaste(nivaa_nokkel)
        )
        brutto = n.kredittar * self.nok_per_kreditt
        return Marginrapport(
            nivaa=n.nokkel,
            leverandor=lev.nokkel,
            inntekt_brutto=brutto,
            app_store_kutt=brutto * self.app_store_kutt,
            gpu_kostnad=lev.kostnad_nok(n.sekund, self.nok_per_usd) * forsok,
            faste_kostnader=self.faste_kroner_per_video,
        )

    def pris_per_levert_video(self, nivaa_nokkel, leverandor_nokkel=None,
                              forsok=1.3):
        """Kva éin levert video faktisk kostar deg - alt inkludert.

        Dette er talet folk gløymer. GPU-prisen er berre ein del: kvar
        levert video dreg med seg lagring, CDN, transkoding og
        moderering uansett kor billeg genereringa var. Med korte klipp
        er den faste delen større enn GPU-en.
        """
        n = self._nivaa(nivaa_nokkel)
        lev = (self.leverandorar[leverandor_nokkel] if leverandor_nokkel
               else self.billegaste(nivaa_nokkel))
        gpu = lev.kostnad_nok(n.sekund, self.nok_per_usd) * forsok
        return gpu + self.faste_kroner_per_video

    def kor_mange_videoar(self, pris_nok, nivaa_nokkel="standard",
                          leverandor_nokkel=None, forsok=1.3,
                          margin=None, bruk=1.0):
        """Kor mange videoar kan denne prisen bere?

        margin er kva du vil sitje att med. bruk er kor stor del av
        kvota folk faktisk brukar - er han under 1.0, kan du LOVE
        fleire videoar enn du betaler for, fordi ikkje alle brukar opp.

        Svarar med talet du trygt kan love.
        """
        margin = self.minste_margin if margin is None else margin
        netto = pris_nok * (1 - self.app_store_kutt)
        budsjett = netto * (1 - margin)
        per_video = self.pris_per_levert_video(nivaa_nokkel,
                                               leverandor_nokkel, forsok)
        if per_video <= 0:
            raise KonfigFeil("Kostnad per video er null - sjekk konfigurasjonen")
        brukte = budsjett / per_video
        return int(brukte / bruk) if bruk > 0 else 0

    def abonnement(self, nivaa_nokkel="standard", pris_nok=None,
                   kredittar=None, bruk=None, leverandor_nokkel=None,
                   forsok=1.3):
        """Rekneskapen for eitt abonnement dersom kvota går til dette nivået.

        Kvota er i kredittar, så kor mange videoar det blir avheng av
        kva nivå abonnenten vel. Verste fall er at han brukar ALT på
        det dyraste nivået - det er tilfellet som må gå i pluss.
        """
        pris = self.abo_pris if pris_nok is None else pris_nok
        kvote = self.abo_kredittar if kredittar is None else kredittar
        bruk = self.abo_venta_bruk if bruk is None else bruk
        n = self._nivaa(nivaa_nokkel)

        netto = pris * (1 - self.app_store_kutt)
        lev = (self.leverandorar[leverandor_nokkel] if leverandor_nokkel
               else self.billegaste(nivaa_nokkel))
        gpu_per_generering = lev.kostnad_nok(n.sekund, self.nok_per_usd)

        genereringar = kvote / n.kredittar
        if self.regenerering_kostar:
            # Kvota tel genereringar. Masar han, får han færre ferdige
            # videoar - men kostnaden din er den same. Hardt tak.
            videoar = genereringar / forsok
        else:
            # Kvota tel ferdige videoar, og du betaler for masinga.
            # Ingen tak på kva ein kravstor brukar kan koste deg.
            videoar = genereringar
            genereringar = videoar * forsok

        def rekneskap(del_av_kvota):
            g = genereringar * del_av_kvota
            v = videoar * del_av_kvota
            return netto - (g * gpu_per_generering
                            + v * self.faste_kroner_per_video)

        return {
            "nivaa": nivaa_nokkel,
            "pris": pris,
            "netto": netto,
            "kredittar": kvote,
            "videoar": videoar,
            "genereringar": genereringar,
            "per_video": self.pris_per_levert_video(
                nivaa_nokkel, leverandor_nokkel, forsok),
            "venta_forteneste": rekneskap(bruk),
            "verste_forteneste": rekneskap(1.0),
        }

    def _nivaa(self, nokkel):
        try:
            return self.nivaa[nokkel]
        except KeyError:
            raise KonfigFeil(f"Ukjent nivå: {nokkel!r}") from None
