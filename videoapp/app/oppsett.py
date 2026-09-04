"""Nøklar og innstillingar frå miljøet.

Ingen nøklar i kode, og ingen stille standardar for dei som betyr noko.
Manglar ein nødvendig nøkkel, skal appen nekte å starte - ikkje starte
halvvegs og feile først når ein brukar prøver noko.

`sjekk()` er meint å køyrast ved oppstart og i deployen din. Ho seier
kva som manglar, samla, i staden for éin feil om gongen.
"""

import os
from dataclasses import dataclass, field

from .auth import MIN_NOKKEL_LENGD


class OppsettFeil(Exception):
    pass


@dataclass
class Oppsett:
    token_nokkel: str = ""
    anthropic_nokkel: str = ""
    leverandor_nokkel: dict = field(default_factory=dict)
    database_url: str = ""
    vassmerke_tekst: str = "videoapp.no"

    @classmethod
    def frae_miljoet(cls, miljo=None):
        m = miljo if miljo is not None else os.environ
        return cls(
            token_nokkel=m.get("VIDEOAPP_TOKEN_NOKKEL", ""),
            anthropic_nokkel=m.get("ANTHROPIC_API_KEY", ""),
            leverandor_nokkel={
                "minimax_hailuo_fast": m.get("MINIMAX_API_NOKKEL", ""),
                "minimax_hailuo_02": m.get("MINIMAX_API_NOKKEL", ""),
                "seedance_lite": m.get("SEEDANCE_API_NOKKEL", ""),
                "runway_turbo": m.get("RUNWAY_API_NOKKEL", ""),
            },
            database_url=m.get("DATABASE_URL", ""),
            vassmerke_tekst=m.get("VASSMERKE_TEKST", "videoapp.no"),
        )

    def manglar(self, prisbok=None):
        """Kva som manglar. Tom liste = klar til å starte."""
        feil = []

        if not self.token_nokkel:
            feil.append(
                "VIDEOAPP_TOKEN_NOKKEL manglar. Lag ein med:\n"
                "    python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"")
        elif len(self.token_nokkel) < MIN_NOKKEL_LENGD:
            feil.append(
                f"VIDEOAPP_TOKEN_NOKKEL er {len(self.token_nokkel)} teikn, "
                f"treng minst {MIN_NOKKEL_LENGD}.")

        if not self.anthropic_nokkel:
            feil.append(
                "ANTHROPIC_API_KEY manglar. Utan han kan vi ikkje moderere, "
                "og moderering feilar lukka - ingen videoar blir laga.")

        if prisbok is not None:
            aktive = [n for n, l in prisbok.leverandorar.items() if l.aktiv]
            med_nokkel = [n for n in aktive if self.leverandor_nokkel.get(n)]
            if not med_nokkel:
                feil.append(
                    "Ingen videoleverandør har nøkkel. Sett minst éin av: "
                    + ", ".join(sorted({
                        {"minimax_hailuo_fast": "MINIMAX_API_NOKKEL",
                         "minimax_hailuo_02": "MINIMAX_API_NOKKEL",
                         "seedance_lite": "SEEDANCE_API_NOKKEL",
                         "runway_turbo": "RUNWAY_API_NOKKEL"}.get(n, n)
                        for n in aktive})))
            else:
                # Tel LEVERANDOERAR, ikkje konfigrader. To MiniMax-modellar
                # deler same noekkel og same selskap - gaar MiniMax ned,
                # gaar begge. Da har du ikkje failover, du har to rader.
                distinkte = {self.leverandor_nokkel[n] for n in med_nokkel}
                if len(distinkte) == 1:
                    feil.append(
                        "ÅTVARING: alle leverandørane med nøkkel deler same "
                        "nøkkel, altså same selskap. Går dei ned, stoppar "
                        "appen. Sett opp ein leverandør til.")

        return feil

    def sjekk(self, prisbok=None):
        """Kastar dersom noko nødvendig manglar. Kall dette ved oppstart."""
        feil = [f for f in self.manglar(prisbok) if not f.startswith("ÅTVARING")]
        if feil:
            raise OppsettFeil(
                "Appen kan ikkje starte:\n\n  " + "\n\n  ".join(feil)
                + "\n\nSjå .env.example.")
        return self

    def er_produksjon(self):
        return bool(self.database_url)
