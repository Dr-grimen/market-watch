#!/usr/bin/env python3
"""Heile appen på ein kommando, utan API-nøklar.

    python3 demo.py

Køyrer den ekte koden - ledger, kø, ruting, moderering, deling, verving.
Berre tre ting er bytta ut med attrappar: videoleverandøren, Claude, og
Apple. Alt anna er nøyaktig det som ville køyrt i produksjon.

Poenget er å sjå at delane heng saman, og at pengane går opp.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.arbeidar import Arbeidar, Bestilling
from app.deling import Deling
from app.ko import Ko
from app.ledger import Ledger
from app.moderering import GODKJENT, Vurdering
from app.pricing import Prisbok
from app.providers.base import Leverandor, Resultat
from app.providers.router import Ruter


class AttrappLeverandor(Leverandor):
    """Later som han lagar video. Ingen nettverk, ingen kostnad."""

    def __init__(self, konfig):
        super().__init__(konfig, api_nokkel="attrapp")

    def generer(self, jobb):
        return Resultat(f"https://cdn.example/{abs(hash(jobb.prompt)) % 10**8}.mp4",
                        self.konfig.nokkel, jobb.sekund, 0.0)


class AttrappModerering:
    """Godtek alt utanom ordet 'stygt', så vi får sett begge utfall."""

    def sjekk(self, prompt, bilde_b64=None, brukar=None):
        if "stygt" in prompt.lower():
            return Vurdering(ok=False, kategori="ulovleg",
                             grunn="Det kan vi ikkje lage video av.")
        return GODKJENT


def steg(n, tekst):
    print(f"\n\033[1m{n}. {tekst}\033[0m")
    print("─" * 62)


def main():
    # Promptforbetringa ville ringt Claude. Byt henne ut.
    import app.arbeidar
    app.arbeidar.forbetre = lambda o, **kw: (
        f"A gentle cinematic shot: {o}. Soft light, slow camera push-in.")

    p = Prisbok()
    lg = Ledger(":memory:")
    ko = Ko(":memory:")
    deling = Deling(lg, p, ":memory:")
    ruter = Ruter(p, {n: AttrappLeverandor(p.leverandorar[n])
                      for n in p.leverandorar})
    bestilling = Bestilling(ko, lg, p, AttrappModerering())
    arbeidar = Arbeidar(ko, lg, ruter, p)

    print("\n\033[1m═══ VIDEOAPP — heile vegen gjennom ═══\033[0m")

    # ------------------------------------------------------------
    steg(1, "Ola lastar ned appen")
    print(f"   Gratiskredittar: {p.gave_ved_registrering}")
    print(f"   Saldo: {lg.saldo('ola')} kredittar")
    print("   → Han kan ikkje lage noko. Det er avgjerda: ingenting gratis.")

    # ------------------------------------------------------------
    steg(2, f"Ola kjøper abonnement — {p.abo_pris:.0f} kr")
    lg.kjop("ola", p.abo_kredittar, idem="apple:txn-001")
    lg.kjop("ola", p.abo_kredittar, idem="apple:txn-001")   # Apple sender om att
    print(f"   Saldo: {lg.saldo('ola')} kredittar")
    print("   (Apple sende kvitteringa to gonger. Idempotensnøkkelen tok det.)")
    a = p.abonnement("standard")
    print(f"   Dette gir {a['videoar']:.0f} standardvideoar. "
          f"Vi tener {a['venta_forteneste']:.0f} kr på han.")

    # ------------------------------------------------------------
    steg(3, "Ola prøver noko appen ikkje lagar")
    _, u = bestilling.bestill("ola", "https://foto/1.jpg", "noko stygt")
    print(f"   Svar: {u.status} — «{u.grunn}»")
    print(f"   Saldo: {lg.saldo('ola')} — ikkje trekt for eit avslag.")

    # ------------------------------------------------------------
    steg(4, "Ola lastar opp eit bilde og skriv tre ord")
    jobb_id, u = bestilling.bestill("ola", "https://foto/hund.jpg",
                                    "få hunden til å springe")
    print(f"   «få hunden til å springe» → i kø som {jobb_id[:8]}")
    print(f"   Plass i kø: {ko.plass_i_ko(jobb_id)}")
    print(f"   Saldo: {lg.saldo('ola')}, reservert: {lg.reservert('ola')}")
    print("   → Reservert, ikkje trekt. Feilar det, får han dei att.")

    # ------------------------------------------------------------
    steg(5, "Ein arbeidar tek jobben")
    res = arbeidar.koyr_ein()
    print(f"   Leverandør: {res.leverandor} (billegaste som klarte nivået)")
    print(f"   Prompt sendt: «{res.prompt_brukt[:52]}…»")
    print(f"   Video: {res.video_url}")
    print(f"   Saldo: {lg.saldo('ola')}, reservert: {lg.reservert('ola')} "
          "— no er dei brukte.")

    # ------------------------------------------------------------
    steg(6, "Ola deler videoen")
    token = deling.lag_lenke(jobb_id, "ola")
    print(f"   Lenke: videoapp.no/v/{token}")
    print(f"   (Tokenet er ikkje jobb-id-en — {jobb_id[:8]}… er skjult.)")
    print("   Videoen blir vassmerkt før deling. Feilar merkinga, deler vi ikkje.")

    # ------------------------------------------------------------
    steg(7, "Kari ser videoen og lastar ned appen")
    deling.opne(token)
    deling.registrer("kari", token)
    print(f"   Kari er registrert som verva av Ola.")
    print(f"   Ola sin saldo: {lg.saldo('ola')} — framleis uendra.")
    print("   → Vi betaler ikkje for eit klikk. Bottar klikkar òg.")

    # ------------------------------------------------------------
    steg(8, "Kari kjøper og lagar sin første video")
    lg.kjop("kari", p.abo_kredittar, idem="apple:txn-002")
    k_jobb, _ = bestilling.bestill("kari", "https://foto/katt.jpg",
                                   "få katten til å danse")
    arbeidar.koyr_ein()
    deling.los_ut("kari")
    print(f"   NO betaler vi. Ola: +{p.verv_til_vervar}, "
          f"Kari: +{p.verv_til_ny} kredittar")
    print(f"   Ola: {lg.saldo('ola')}   Kari: {lg.saldo('kari')}")

    # ------------------------------------------------------------
    steg(9, "Ein farmar prøver seg")
    for i in range(p.verv_maks + 8):
        t = deling.lag_lenke(f"farm{i}", "farmar")
        deling.registrer(f"botte{i}", t)
        deling.los_ut(f"botte{i}")
    s = deling.statistikk("farmar")
    print(f"   Lagde {p.verv_maks + 8} kontoar, fekk betalt for {s['belont']}")
    print(f"   Saldo: {lg.saldo('farmar')} — taket heldt.")

    # ------------------------------------------------------------
    steg(10, "Går rekneskapen opp?")
    print(f"   Alle posteringar summerer til null: {lg.stemmer()}")
    print(f"   Kø: {ko.tal()}")
    reservert_totalt = sum(lg.reservert(b) for b in
                           ("ola", "kari", "farmar"))
    print(f"   Kredittar hengande i reservasjon: {reservert_totalt}")
    print("\n   Ingen har betalt for ein video dei ikkje fekk.\n")


if __name__ == "__main__":
    main()
