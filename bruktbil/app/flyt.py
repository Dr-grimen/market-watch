"""Flyten gjennom handelen.

All logikk som endrar ein handel bur her. Webrutene gjer to ting: finn rett
handel, og kall ein funksjon herifrå. Då kan heile forretningslogikken testast
utan å starte ein webtenar, og reglane kan ikkje omgåast ved å kalle rutene i
feil rekkjefølgje.

Regelen som ber heile appen: *ingen ting går bakover*. Steg blir låst etter
kvart som dei blir gjorde, og signaturane er bundne til kontraktteksten slik
han såg ut då dei blei sette.
"""

from __future__ import annotations

from . import kontrakt
from .modell import (
    GEBYR_KRONER,
    Feil,
    Handel,
    Rolle,
    Steg,
    kontonummer_er_gyldig,
    maskert,
    ny_handel,
    no_tid,
    normaliser_skilt,
)
from .tenester import bankid, betaling, eigarskifte, finn, forsikring, kjoretoy, laan


def _krev(steg_no: str, venta: Steg, kva: str) -> None:
    if steg_no != venta.value:
        raise Feil(f"{kva} kan ikkje gjerast no (handelen står på «{steg_no}»).")


# --- 1. seljaren opprettar salet ------------------------------------------


def opprett_sal(
    *,
    skilt: str = "",
    finn_lenke: str = "",
    pris: int = 0,
    namn: str = "",
    fnr: str = "",
    telefon: str = "",
    epost: str = "",
    adresse: str = "",
    kontonummer: str = "",
) -> Handel:
    if finn_lenke.strip():
        annonse = finn.les(finn_lenke)
        skilt = annonse["skilt"]
        pris = pris or annonse["pris"]
    skilt = normaliser_skilt(skilt)
    pris = int(pris or 0)
    if pris <= 0:
        raise Feil("Prisen må vere høgare enn null.")
    bankid.identifiser(fnr, namn)
    if kontonummer and not kontonummer_er_gyldig(kontonummer):
        raise Feil("Kontonummeret er ikkje eit gyldig norsk kontonummer.")

    h = ny_handel()
    h.skilt = skilt
    h.bil = kjoretoy.hent(skilt)
    h.pris = pris
    h.seljar.namn = namn.strip()
    h.seljar.fnr_maskert = maskert(fnr)
    h.seljar.telefon = telefon.strip()
    h.seljar.epost = epost.strip()
    h.seljar.adresse = adresse.strip()
    h.seljar.kontonummer = kontonummer.strip()
    h.steg = Steg.VENTAR_KJOPAR.value
    h.noter(f"Sal oppretta for {skilt} til {pris} kr", Rolle.SELJAR.value)
    if h.bil.get("merknader"):
        h.noter("Oppslaget gav merknader: " + "; ".join(h.bil["merknader"]))
    return h


# --- 2. kjøparen blir med -------------------------------------------------


def bli_med(
    h: Handel,
    *,
    namn: str,
    fnr: str,
    telefon: str = "",
    epost: str = "",
    adresse: str = "",
) -> Handel:
    _krev(h.steg, Steg.VENTAR_KJOPAR, "Å bli med i handelen")
    bankid.identifiser(fnr, namn)
    h.kjopar.namn = namn.strip()
    h.kjopar.fnr_maskert = maskert(fnr)
    h.kjopar.telefon = telefon.strip()
    h.kjopar.epost = epost.strip()
    h.kjopar.adresse = adresse.strip()
    h.steg = Steg.VILKAAR.value
    h.noter(f"{h.kjopar.namn} blei med i handelen", Rolle.KJOPAR.value)
    return h


# --- 3. vilkåra -----------------------------------------------------------


def set_vilkaar(
    h: Handel,
    rolle: str,
    *,
    pris: int | None = None,
    utstyr: str = "",
    kjende_feil: str = "",
    overlevering: str = "",
    kilometerstand: int | None = None,
) -> Handel:
    """Seljaren fyller ut det oppslaget ikkje veit. Låst når nokon har signert."""
    if rolle != Rolle.SELJAR.value:
        raise Feil("Berre seljaren kan setje vilkåra.")
    if h.seljar.signert or h.kjopar.signert:
        raise Feil("Vilkåra kan ikkje endrast etter at nokon har signert.")
    _krev(h.steg, Steg.VILKAAR, "Å endre vilkåra")
    if pris is not None and int(pris) > 0:
        h.pris = int(pris)
    if kilometerstand is not None and int(kilometerstand) > 0:
        h.bil["kilometerstand"] = int(kilometerstand)
    h.vilkaar = {
        "utstyr": utstyr.strip(),
        "kjende_feil": kjende_feil.strip(),
        "overlevering": overlevering.strip(),
    }
    h.noter("Vilkåra er sette", rolle)
    return h


def send_til_signering(h: Handel, rolle: str) -> Handel:
    if rolle != Rolle.SELJAR.value:
        raise Feil("Berre seljaren sender kontrakten til signering.")
    _krev(h.steg, Steg.VILKAAR, "Å sende kontrakten til signering")
    if not h.kjopar.er_med:
        raise Feil("Kjøparen er ikkje med i handelen enno.")
    if not h.seljar.kontonummer:
        raise Feil("Seljaren må leggje inn kontonummer for oppgjeret.")
    h.steg = Steg.SIGNERING.value
    h.noter("Kontrakten er klar til signering", rolle)
    return h


# --- 4. signering ---------------------------------------------------------


def start_signering(h: Handel, rolle: str) -> dict:
    """Startar BankID-signeringa. Partane er alt identifiserte, så her skjer
    ingen ting som endrar kontraktteksten."""
    _krev(h.steg, Steg.SIGNERING, "Signering")
    part = h.part(rolle)
    if part.signert:
        raise Feil("Du har allereie signert.")
    okt = bankid.start(kontrakt.fingeravtrykk(h), part.namn)
    h.vilkaar.setdefault("_okter", {})[rolle] = {
        "ref": okt["ref"],
        "dokument": okt["dokument"],
    }
    h.noter("BankID-signering starta", rolle)
    return okt


def fullfor_signering(h: Handel, rolle: str, *, kode: str) -> Handel:
    _krev(h.steg, Steg.SIGNERING, "Signering")
    part = h.part(rolle)
    okt = (h.vilkaar.get("_okter") or {}).get(rolle)
    if not okt:
        raise Feil("Ingen signering er starta. Trykk «Signer» først.")
    if okt["dokument"] != kontrakt.fingeravtrykk(h):
        raise Feil("Kontrakten er endra etter at signeringa starta. Start på nytt.")
    kvittering = bankid.stadfest(okt["ref"], kode)
    part.signert = kvittering["tid"]
    part.signatur_ref = kvittering["ref"]
    if not h.kontrakt_signatur:
        h.kontrakt_signatur = okt["dokument"]
    h.noter(f"{part.namn} signerte med BankID", rolle)
    if h.begge_har_signert:
        h.steg = Steg.BETALING.value
        h.noter("Begge har signert. Kontrakten er bindande.")
    return h


# --- 5. betaling ----------------------------------------------------------


def opprett_betaling(h: Handel, rolle: str) -> Handel:
    _krev(h.steg, Steg.BETALING, "Betaling")
    if rolle != Rolle.KJOPAR.value:
        raise Feil("Det er kjøparen som betaler inn.")
    if h.betaling:
        return h
    if not kontrakt.er_urørt(h):
        raise Feil("Kontrakten stemmer ikkje med det som blei signert.")
    h.betaling = betaling.opprett(
        belop=h.totalt_aa_betale,
        gebyr=GEBYR_KRONER,
        referanse=f"Bilkjøp {h.skilt} ({h.id})",
        til_konto=h.seljar.kontonummer,
    )
    h.noter(f"Betaling oppretta: {h.totalt_aa_betale} kr til klientkonto", rolle)
    return h


def stadfest_betaling(h: Handel) -> Handel:
    """Kalla av banken sitt webhook. I demoen av ein knapp."""
    _krev(h.steg, Steg.BETALING, "Betaling")
    if not h.betaling:
        raise Feil("Ingen betaling er oppretta.")
    h.betaling = betaling.stadfest_innbetaling(h.betaling["id"])
    h.steg = Steg.EIGARSKIFTE.value
    h.noter("Pengane står trygt på klientkonto")
    return h


# --- 6. eigarskifte -------------------------------------------------------


def send_salsmelding(h: Handel, rolle: str) -> Handel:
    _krev(h.steg, Steg.EIGARSKIFTE, "Salsmelding")
    if rolle != Rolle.SELJAR.value:
        raise Feil("Seljaren sender salsmeldinga.")
    if h.eigarskifte:
        raise Feil("Salsmeldinga er allereie sendt.")
    h.eigarskifte = eigarskifte.send_salsmelding(
        h.skilt, h.seljar.namn, h.kjopar.namn, h.pris
    )
    h.noter("Salsmelding sendt til Statens vegvesen", rolle)
    return h


def stadfest_salsmelding(h: Handel, rolle: str) -> Handel:
    """Kjøparen stadfestar. Går det gjennom, betaler vi ut same augeblink."""
    _krev(h.steg, Steg.EIGARSKIFTE, "Stadfesting av salsmelding")
    if rolle != Rolle.KJOPAR.value:
        raise Feil("Kjøparen stadfestar salsmeldinga.")
    if not h.eigarskifte:
        raise Feil("Seljaren har ikkje sendt salsmelding enno.")
    h.eigarskifte = eigarskifte.stadfest(h.eigarskifte["id"])
    h.eigarskifte = eigarskifte.fullfor(h.eigarskifte["id"])
    h.noter("Eigarskiftet er gjennomført — bilen står i kjøparen sitt namn", rolle)
    h.betaling = betaling.frigi(h.betaling["id"])
    h.steg = Steg.FULLFORT.value
    h.noter(f"{h.pris} kr utbetalt til seljaren. Handelen er fullført.")
    return h


# --- forsikring og lån (valfritt, når som helst før eigarskiftet) ---------


def forsikringstilbod(h: Handel) -> list:
    return forsikring.tilbod(h.bil, h.pris)


def vel_forsikring(h: Handel, rolle: str, selskap: str) -> Handel:
    if rolle != Rolle.KJOPAR.value:
        raise Feil("Kjøparen vel forsikring.")
    h.forsikring = forsikring.teikn(selskap, forsikringstilbod(h))
    h.noter(f"Forsikring teikna hos {selskap}", rolle)
    return h


def laanetilbod(h: Handel, eigenkapital: int) -> list:
    return laan.tilbod(h.bil, h.pris, eigenkapital)


def vel_laan(h: Handel, rolle: str, bank: str, eigenkapital: int) -> Handel:
    if rolle != Rolle.KJOPAR.value:
        raise Feil("Kjøparen søkjer lån.")
    h.laan = laan.sok(bank, laanetilbod(h, eigenkapital))
    h.noter(f"Lån førehandsgodkjent hos {bank}", rolle)
    return h


# --- avbrot ---------------------------------------------------------------


def avbryt(h: Handel, rolle: str, grunn: str = "") -> Handel:
    if h.steg in (Steg.FULLFORT.value, Steg.AVBROTEN.value):
        raise Feil("Handelen er avslutta og kan ikkje avbrytast.")
    if h.eigarskifte.get("status") == eigarskifte.FULLFORT:
        raise Feil("Eigarskiftet er gjennomført. Kontakt kundestøtte.")
    if h.betaling:
        h.betaling = betaling.refunder(h.betaling["id"])
        h.noter("Innbetalinga er refundert til kjøparen")
    h.steg = Steg.AVBROTEN.value
    h.noter(f"Handelen avbroten. {grunn}".strip(), rolle)
    return h


# --- hjelp til grensesnittet ---------------------------------------------


def neste_steg_tekst(h: Handel, rolle: str) -> str:
    """Éi setning: kva ventar vi på no, sett frå denne rolla."""
    part = h.part(rolle)
    er_seljar = rolle == Rolle.SELJAR.value
    if h.steg == Steg.VENTAR_KJOPAR.value:
        return (
            f"Send delingskoden {h.kode} til kjøparen."
            if er_seljar
            else "Ventar på at seljaren gjer klar handelen."
        )
    if h.steg == Steg.VILKAAR.value:
        return (
            "Fyll ut vilkåra og send kontrakten til signering."
            if er_seljar
            else "Seljaren fyller ut vilkåra. Du får kontrakten til gjennomlesing."
        )
    if h.steg == Steg.SIGNERING.value:
        if part.signert:
            return "Du har signert. Ventar på motparten."
        return "Les gjennom kontrakten og signer med BankID."
    if h.steg == Steg.BETALING.value:
        if er_seljar:
            return "Ventar på at kjøparen betaler inn til klientkonto."
        return f"Betal {h.totalt_aa_betale} kr inn til klientkonto."
    if h.steg == Steg.EIGARSKIFTE.value:
        if not h.eigarskifte:
            return (
                "Send salsmelding til Vegvesenet."
                if er_seljar
                else "Ventar på at seljaren sender salsmelding."
            )
        return (
            "Ventar på at kjøparen stadfestar salsmeldinga."
            if er_seljar
            else "Stadfest salsmeldinga, så blir pengane utbetalte."
        )
    if h.steg == Steg.FULLFORT.value:
        return "Ferdig. Bilen er overført og pengane er utbetalte."
    return "Handelen er avbroten."
