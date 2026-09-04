"""Kjøpekontrakten.

Kontrakten blir laga av dei same data som begge partar har sett i appen — ikkje
skriven inn på nytt. Det er heile grunnen til at han blir rett: prisen i
kontrakten *er* prisen i oppgjeret, kilometerstanden *er* den som stod i
oppslaget, og ingen av delane kan endrast etter at nokon har signert.

Salet er mellom to privatpersonar. Då gjeld kjøpslova, ikkje forbrukarkjøpslova:
kjøparen har svakare vern, og «seld som han står» er lov — men set ikkje
seljaren fri om han har halde noko skjult (kjøpslova § 19).
"""

from __future__ import annotations

import hashlib

from .modell import GEBYR_KRONER, Handel

STANDARDVILKAAR = [
    "Bilen blir seld som han står, jf. kjøpslova § 19. Kjøparen har undersøkt "
    "bilen, eller valt å la vere.",
    "Seljaren stadfestar at opplysningane i kontrakten er rette, og at han ikkje "
    "kjenner til feil eller skadar utover det som står under «Kjende feil».",
    "Seljaren stadfestar at bilen er fri for heftingar, eller at heftingane som "
    "står i kontrakten blir innfridde av oppgjeret før pengane blir utbetalte.",
    "Kjøpesummen blir betalt inn på klientkonto, og utbetalt til seljaren først "
    "når eigarskiftet er gjennomført hos Statens vegvesen.",
    "Risikoen for bilen går over på kjøparen ved overlevering av nøklar og bil.",
    "Kjøparen pliktar å ha forsikring på bilen frå det tidspunktet han står "
    "registrert på han.",
    "Partane har signert elektronisk med BankID. Signaturane er knytte til "
    "denne teksten; blir teksten endra, fell signaturane bort.",
]


def _kr(tal: int) -> str:
    return f"{int(tal):,}".replace(",", " ") + " kr"


def tekst(h: Handel) -> str:
    """Kontrakten som rein tekst. Dette er det signaturane festar seg til."""
    bil = h.bil or {}
    v = h.vilkaar or {}
    linjer = [
        "KJØPEKONTRAKT FOR BRUKT MOTORVOGN",
        "mellom to privatpersonar",
        "",
        f"Handel-ID: {h.id}",
        f"Oppretta: {h.oppretta}",
        "",
        "1. PARTAR",
        f"   Seljar: {h.seljar.namn or '—'}",
        f"           fødselsnr. {h.seljar.fnr_maskert or '—'}",
        f"           {h.seljar.adresse or '—'}",
        f"           tlf. {h.seljar.telefon or '—'}, {h.seljar.epost or '—'}",
        f"   Kjøpar: {h.kjopar.namn or '—'}",
        f"           fødselsnr. {h.kjopar.fnr_maskert or '—'}",
        f"           {h.kjopar.adresse or '—'}",
        f"           tlf. {h.kjopar.telefon or '—'}, {h.kjopar.epost or '—'}",
        "",
        "2. KJØRETØYET",
        f"   Registreringsnummer: {h.skilt}",
        f"   Merke og modell:     {bil.get('merke', '—')} {bil.get('modell', '')}",
        f"   Årsmodell:           {bil.get('aarsmodell', '—')}",
        f"   Drivstoff/girkasse:  {bil.get('drivstoff', '—')} / {bil.get('girkasse', '—')}",
        f"   Kilometerstand:      {bil.get('kilometerstand', '—')} km",
        f"   Frist EU-kontroll:   {bil.get('eu_kontroll_frist', '—')}",
        f"   Opplysningane er henta frå: {bil.get('kjelde', '—')}",
        "",
        "3. PRIS OG OPPGJER",
        f"   Kjøpesum:               {_kr(h.pris)}",
        f"   Omregistreringsavgift:  {_kr(h.omregistreringsavgift)} (estimat)",
        f"   Gebyr for tenesta:      {_kr(GEBYR_KRONER)}",
        f"   Kjøparen betaler inn:   {_kr(h.totalt_aa_betale)}",
        f"   Utbetaling til seljar:  {_kr(h.pris)} til konto {h.seljar.kontonummer or '—'}",
        "",
        "4. UTSTYR SOM FØLGJER MED",
        f"   {v.get('utstyr') or 'To nøklar, servicehefte og instruksjonsbok.'}",
        "",
        "5. KJENDE FEIL OG MANGLAR",
        f"   {v.get('kjende_feil') or 'Ingen oppgjevne.'}",
        "",
        "6. HEFTINGAR",
    ]
    heftingar = bil.get("heftingar") or []
    if heftingar:
        for heft in heftingar:
            linjer.append(
                f"   {heft['långjevar']}: {_kr(heft['belop'])} — blir innfridd av oppgjeret."
            )
    else:
        linjer.append("   Ingen registrerte heftingar på oppslagstidspunktet.")
    linjer += [
        "",
        "7. OVERLEVERING",
        f"   {v.get('overlevering') or 'Etter avtale mellom partane, etter at eigarskiftet er meldt.'}",
        "",
        "8. VILKÅR",
    ]
    linjer += [f"   {nr}. {t}" for nr, t in enumerate(STANDARDVILKAAR, start=1)]
    linjer += ["", "9. SIGNATURAR"]
    for part in (h.seljar, h.kjopar):
        if part.signert:
            linjer.append(
                f"   {part.rolle.capitalize()}: {part.namn} — BankID {part.signatur_ref} "
                f"— {part.signert}"
            )
        else:
            linjer.append(f"   {part.rolle.capitalize()}: {part.namn or '—'} — ikkje signert")
    return "\n".join(linjer)


def signaturgrunnlag(h: Handel) -> str:
    """Teksten utan signaturbolken — det som faktisk blir signert.

    Elles ville seljaren sin signatur endra dokumentet kjøparen skal signere,
    og den første signaturen ville bli ugyldig i det andaren kom.
    """
    return tekst(h).split("\n9. SIGNATURAR")[0]


def fingeravtrykk(h: Handel) -> str:
    return hashlib.sha256(signaturgrunnlag(h).encode("utf-8")).hexdigest()


def er_urørt(h: Handel) -> bool:
    """Stemmer kontrakten framleis med det som blei signert?"""
    if not h.kontrakt_signatur:
        return True
    return h.kontrakt_signatur == fingeravtrykk(h)
