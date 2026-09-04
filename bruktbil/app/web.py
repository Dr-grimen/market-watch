"""Webappen: rutene og sidene.

Rutene gjer tre ting og ikkje meir: hentar handelen, kallar `flyt`, og teiknar
resultatet. All logikk som avgjer *om* noko er lov ligg i `flyt`, slik at ho
ikkje kan omgåast ved å kalle rutene i ei anna rekkjefølgje enn appen legg opp
til.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import flyt, kontrakt, lager, mal
from .modell import GEBYR_KRONER, Feil, Rolle, Steg
from .tenester import betaling as betalingsteneste
from .tenester import kjoretoy

app = FastAPI(title="Bruktbil", docs_url="/api/docs")
lager.klargjer()

SELJAR = Rolle.SELJAR.value
KJOPAR = Rolle.KJOPAR.value


def lenke(h, rolle: str, hale: str = "", **sporsmaal) -> str:
    token = h.part(rolle).token
    url = f"/h/{h.id}/{rolle}/{token}{hale}"
    reine = {k: v for k, v in sporsmaal.items() if v}
    return f"{url}?{urlencode(reine)}" if reine else url


def tilbake(h, rolle: str, melding: str = "", feil: str = "") -> RedirectResponse:
    return RedirectResponse(lenke(h, rolle, melding=melding, feil=feil), status_code=303)


@app.exception_handler(Feil)
async def feilhandsamar(request: Request, exc: Feil):
    kropp = f"<div class='kort'><h1>Det gjekk ikkje</h1><p>{mal.e(str(exc))}</p>" \
            "<a class='lenkeknapp' href='/'>Til framsida</a></div>"
    return HTMLResponse(mal.side("Feil", kropp), status_code=400)


# --- framside -------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def framside(feil: str = "", melding: str = ""):
    kropp = f"""
<h1>Sel eller kjøp bruktbil<br>utan å ta sjansen</h1>
<p class="svak">Skiltnummeret hentar bilen. Appen lagar kontrakten, tek imot
pengane på klientkonto, og betaler dei ut først når bilen står i kjøparen sitt
namn. {mal.kr(GEBYR_KRONER)} for heile handelen.</p>

<div class="kort">
<h2 style="margin-top:0">Eg skal selje</h2>
<form method="post" action="/nytt-sal">
  <label>Skiltnummer</label>
  <input name="skilt" placeholder="DB12345" autocapitalize="characters">
  <label>… eller lenke til Finn-annonsen</label>
  <input name="finn_lenke" placeholder="https://www.finn.no/…?finnkode=300000001">
  <label>Pris</label>
  <input name="pris" inputmode="numeric" placeholder="179000">
  <label>Namnet ditt</label>
  <input name="namn" required placeholder="Ola Nordmann">
  <label>Fødselsnummer (BankID)</label>
  <input name="fnr" inputmode="numeric" required placeholder="11 siffer">
  <label>Kontonummer for oppgjeret</label>
  <input name="kontonummer" inputmode="numeric" placeholder="11 siffer">
  <label>Telefon</label><input name="telefon" inputmode="tel">
  <label>Adresse</label><input name="adresse">
  <button>Hent bilen og opprett handel</button>
</form>
</div>

<div class="kort">
<h2 style="margin-top:0">Eg skal kjøpe</h2>
<p class="svak">Har du fått ein delingskode av seljaren?</p>
<form method="post" action="/bli-med">
  <label>Delingskode</label>
  <input name="kode" required placeholder="ABC123" autocapitalize="characters">
  <label>Namnet ditt</label><input name="namn" required>
  <label>Fødselsnummer (BankID)</label>
  <input name="fnr" inputmode="numeric" required placeholder="11 siffer">
  <label>Telefon</label><input name="telefon" inputmode="tel">
  <label>Adresse</label><input name="adresse">
  <button>Bli med i handelen</button>
</form>
</div>

<p class="svak">Demo-skilt som gir ferdig utfylte data: <b>DB12345</b> (Golf) og
<b>EL45678</b> (Tesla med pant). Alle andre skilt gir oppdikta data.</p>
"""
    return mal.side("Bruktbil", kropp, melding=melding, feil=feil)


@app.post("/nytt-sal")
def nytt_sal(
    skilt: str = Form(""),
    finn_lenke: str = Form(""),
    pris: str = Form("0"),
    namn: str = Form(...),
    fnr: str = Form(...),
    kontonummer: str = Form(""),
    telefon: str = Form(""),
    adresse: str = Form(""),
):
    h = flyt.opprett_sal(
        skilt=skilt,
        finn_lenke=finn_lenke,
        pris=int(pris or 0) if str(pris).strip().isdigit() else 0,
        namn=namn,
        fnr=fnr,
        kontonummer=kontonummer,
        telefon=telefon,
        adresse=adresse,
    )
    lager.lagre(h)
    return RedirectResponse(lenke(h, SELJAR), status_code=303)


@app.post("/bli-med")
def bli_med(
    kode: str = Form(...),
    namn: str = Form(...),
    fnr: str = Form(...),
    telefon: str = Form(""),
    adresse: str = Form(""),
):
    h = lager.hent_med_kode(kode)
    flyt.bli_med(h, namn=namn, fnr=fnr, telefon=telefon, adresse=adresse)
    lager.lagre(h)
    return RedirectResponse(lenke(h, KJOPAR), status_code=303)


# --- handelen -------------------------------------------------------------


@app.get("/h/{hid}/{rolle}/{token}", response_class=HTMLResponse)
def handelsside(hid: str, rolle: str, token: str, melding: str = "", feil: str = ""):
    h = lager.hent_med_token(hid, rolle, token)
    kropp = (
        mal.stig(h)
        + f"<div class='kort tett'><b>{mal.e(flyt.neste_steg_tekst(h, rolle))}</b></div>"
        + mal.bilkort(h)
        + mal.prisrad(h)
        + _handlingar(h, rolle)
        + f"<a class='lenkeknapp' href='{lenke(h, rolle, '/kontrakt')}'>Les kontrakten</a>"
        + _sidetenester(h, rolle)
        + mal.logg(h)
        + _avbrot(h, rolle)
    )
    return mal.side(f"{h.bil.get('merke','Handel')} {h.skilt}", kropp, melding, feil)


def _handlingar(h, rolle: str) -> str:
    """Den eine knappen som er relevant akkurat no, for akkurat denne parten."""
    steg, er_seljar = h.steg, rolle == SELJAR
    u = lenke(h, rolle)

    if steg == Steg.VENTAR_KJOPAR.value and er_seljar:
        return f"""<div class="kort">
<h2 style="margin-top:0">Del denne koden med kjøparen</h2>
<div class="kode">{mal.e(h.kode)}</div>
<p class="svak">Kjøparen skriv koden inn på framsida. Då — og først då — får han
sjå opplysningane om bilen og kontrakten.</p></div>"""

    if steg == Steg.VILKAAR.value and er_seljar:
        v = h.vilkaar or {}
        return f"""<div class="kort">
<h2 style="margin-top:0">Vilkåra</h2>
<form method="post" action="{u}/vilkaar">
  <label>Pris</label><input name="pris" inputmode="numeric" value="{h.pris}">
  <label>Kilometerstand no</label>
  <input name="kilometerstand" inputmode="numeric" value="{mal.e(h.bil.get('kilometerstand',''))}">
  <label>Utstyr som følgjer med</label>
  <textarea name="utstyr" placeholder="To nøklar, sommardekk på felg, servicehefte">{mal.e(v.get('utstyr',''))}</textarea>
  <label>Kjende feil og manglar</label>
  <textarea name="kjende_feil" placeholder="Skriv alt du veit om. Det du fortel her, kan du ikkje bli klaga på seinare.">{mal.e(v.get('kjende_feil',''))}</textarea>
  <label>Overlevering</label>
  <input name="overlevering" value="{mal.e(v.get('overlevering',''))}" placeholder="Laurdag 12. kl 14, Bergen">
  <button>Lagre vilkåra</button>
</form>
<form method="post" action="{u}/til-signering">
  <button class="mild">Send kontrakten til signering</button>
</form></div>"""

    if steg == Steg.SIGNERING.value:
        part = h.part(rolle)
        if part.signert:
            return f"""<div class="kort"><span class="merke">Signert</span>
<p class="svak" style="margin-top:10px">Du signerte {mal.e(part.signert[:16].replace('T',' '))}.
Ventar på {mal.e(h.motpart(rolle).namn)}.</p></div>"""
        return f"""<div class="kort">
<h2 style="margin-top:0">Signer med BankID</h2>
<p class="svak">Les kontrakten først. Signaturen festar seg til teksten slik han
står no — blir noko endra etterpå, fell signaturen bort.</p>
<form method="post" action="{u}/signer"><button>Start BankID-signering</button></form></div>"""

    if steg == Steg.BETALING.value:
        if er_seljar:
            return """<div class="kort"><p>Kontrakten er bindande. Ventar på at
kjøparen betaler inn til klientkonto.</p></div>"""
        if not h.betaling:
            return f"""<div class="kort">
<h2 style="margin-top:0">Betal til klientkonto</h2>
<p class="svak">Pengane står trygt hos oss til bilen er overført. Blir handelen
avlyst, får du alt tilbake.</p>
<form method="post" action="{u}/betal"><button>Opprett betaling på {mal.kr(h.totalt_aa_betale)}</button></form></div>"""
        b = h.betaling
        return f"""<div class="kort">
<h2 style="margin-top:0">Overfør frå banken din</h2>
<div class="rad"><span>Til konto</span><span>{mal.e(b['klientkonto'])}</span></div>
<div class="rad"><span>Beløp</span><span>{mal.kr(b['belop'])}</span></div>
<div class="rad"><span>Melding</span><span>{mal.e(b['referanse'])}</span></div>
<p class="svak" style="margin-top:12px">I ein ekte app registrerer banken innbetalinga
sjølv. Her trykkjer du knappen.</p>
<form method="post" action="{u}/betal/stadfest"><button>Eg har betalt</button></form></div>"""

    if steg == Steg.EIGARSKIFTE.value:
        if not h.eigarskifte:
            if er_seljar:
                return f"""<div class="kort">
<h2 style="margin-top:0">Send salsmelding</h2>
<p class="svak">Pengane står på klientkonto. Meld salet til Vegvesenet, så
stadfestar kjøparen.</p>
<form method="post" action="{u}/salsmelding"><button>Send salsmelding</button></form></div>"""
            return """<div class="kort"><p>Pengane dine står trygt. Ventar på at
seljaren sender salsmelding til Vegvesenet.</p></div>"""
        if er_seljar:
            return """<div class="kort"><p>Salsmeldinga er sendt. Når kjøparen
stadfestar, blir pengane utbetalte til deg med ein gong.</p></div>"""
        return f"""<div class="kort">
<h2 style="margin-top:0">Stadfest salsmeldinga</h2>
<p class="svak">Har du fått bilen og nøklane? Stadfest, så blir eigarskiftet
gjennomført og seljaren får pengane.</p>
<form method="post" action="{u}/salsmelding/stadfest"><button>Stadfest og gjer opp</button></form></div>"""

    if steg == Steg.FULLFORT.value:
        kvittering = (
            f"<div class='rad'><span>Utbetalt til seljaren</span><span>{mal.kr(h.pris)}</span></div>"
            f"<div class='rad'><span>Eigarskifte</span><span>{mal.e(h.eigarskifte.get('fullfort','')[:10])}</span></div>"
        )
        return f"""<div class="kort"><span class="merke">Fullført</span>
<h2>Kvittering</h2>{kvittering}</div>"""

    return """<div class="kort"><p>Handelen er avbroten. Er det betalt inn noko,
er det refundert.</p></div>"""


def _sidetenester(h, rolle: str) -> str:
    """Forsikring og lån. Berre for kjøparen, og berre medan det er nyttig."""
    if rolle != KJOPAR or h.steg in (Steg.FULLFORT.value, Steg.AVBROTEN.value):
        return ""
    u = lenke(h, rolle)
    ut = []

    if h.forsikring:
        f = h.forsikring
        ut.append(
            f"<div class='kort tett'><span class='merke'>Forsikring</span>"
            f"<div class='rad'><span>{mal.e(f['selskap'])}</span>"
            f"<span>{mal.kr(f['maanadspris'])}/md</span></div></div>"
        )
    else:
        val = "".join(
            f"<option value='{mal.e(t['selskap'])}'>{mal.e(t['selskap'])} — "
            f"{mal.kr(t['maanadspris'])}/md — {mal.e(t['dekning'])}</option>"
            for t in flyt.forsikringstilbod(h)
        )
        ut.append(f"""<div class="kort">
<h2 style="margin-top:0">Forsikring frå dagen du overtek</h2>
<form method="post" action="{u}/forsikring">
<select name="selskap">{val}</select><button class="mild">Teikn forsikring</button></form></div>""")

    if h.laan:
        laanet = h.laan
        ut.append(
            f"<div class='kort tett'><span class='merke'>Lån førehandsgodkjent</span>"
            f"<div class='rad'><span>{mal.e(laanet['bank'])} · {laanet['rente']} %</span>"
            f"<span>{mal.kr(laanet['maanadsbelop'])}/md</span></div></div>"
        )
    else:
        ut.append(f"""<div class="kort">
<h2 style="margin-top:0">Treng du lån?</h2>
<form method="post" action="{u}/laan">
<label>Eigenkapital</label><input name="eigenkapital" inputmode="numeric" value="0">
<label>Nedbetalingstid</label>
<select name="aar"><option value="3">3 år</option><option value="5" selected>5 år</option>
<option value="7">7 år</option></select>
<button class="mild">Hent lånetilbod</button></form></div>""")
    return "".join(ut)


def _avbrot(h, rolle: str) -> str:
    if h.steg in (Steg.FULLFORT.value, Steg.AVBROTEN.value):
        return ""
    return f"""<form method="post" action="{lenke(h, rolle)}/avbryt">
<input type="hidden" name="grunn" value="">
<button class="mild">Avbryt handelen</button></form>"""


# --- handlingar -----------------------------------------------------------


def _last(hid, rolle, token):
    return lager.hent_med_token(hid, rolle, token)


@app.post("/h/{hid}/{rolle}/{token}/vilkaar")
def sett_vilkaar(
    hid: str,
    rolle: str,
    token: str,
    pris: str = Form("0"),
    kilometerstand: str = Form("0"),
    utstyr: str = Form(""),
    kjende_feil: str = Form(""),
    overlevering: str = Form(""),
):
    h = _last(hid, rolle, token)
    flyt.set_vilkaar(
        h,
        rolle,
        pris=int(pris) if pris.strip().isdigit() else None,
        kilometerstand=int(kilometerstand) if kilometerstand.strip().isdigit() else None,
        utstyr=utstyr,
        kjende_feil=kjende_feil,
        overlevering=overlevering,
    )
    lager.lagre(h)
    return tilbake(h, rolle, "Vilkåra er lagra.")


@app.post("/h/{hid}/{rolle}/{token}/til-signering")
def til_signering(hid: str, rolle: str, token: str):
    h = _last(hid, rolle, token)
    flyt.send_til_signering(h, rolle)
    lager.lagre(h)
    return tilbake(h, rolle, "Kontrakten er sendt til signering.")


@app.post("/h/{hid}/{rolle}/{token}/signer", response_class=HTMLResponse)
def signer(hid: str, rolle: str, token: str):
    h = _last(hid, rolle, token)
    okt = flyt.start_signering(h, rolle)
    lager.lagre(h)
    kropp = f"""<div class="kort">
<h1 style="margin-top:0">BankID</h1>
<p class="svak">Opne BankID-appen og skriv inn koden. I demoen står han her:</p>
<div class="kode">{mal.e(okt['kode'])}</div>
<form method="post" action="{lenke(h, rolle)}/signer/stadfest">
<label>Kode frå BankID</label><input name="kode" inputmode="numeric" required autofocus>
<button>Signer kontrakten</button></form>
<a class="lenkeknapp" href="{lenke(h, rolle)}">Avbryt</a></div>"""
    return mal.side("Signering", kropp)


@app.post("/h/{hid}/{rolle}/{token}/signer/stadfest")
def signer_stadfest(hid: str, rolle: str, token: str, kode: str = Form(...)):
    h = _last(hid, rolle, token)
    try:
        flyt.fullfor_signering(h, rolle, kode=kode)
    except Feil as f:
        lager.lagre(h)
        return tilbake(h, rolle, feil=str(f))
    lager.lagre(h)
    return tilbake(h, rolle, "Kontrakten er signert.")


@app.post("/h/{hid}/{rolle}/{token}/betal")
def betal(hid: str, rolle: str, token: str):
    h = _last(hid, rolle, token)
    flyt.opprett_betaling(h, rolle)
    lager.lagre(h)
    return tilbake(h, rolle)


@app.post("/h/{hid}/{rolle}/{token}/betal/stadfest")
def betal_stadfest(hid: str, rolle: str, token: str):
    h = _last(hid, rolle, token)
    flyt.stadfest_betaling(h)
    lager.lagre(h)
    return tilbake(h, rolle, "Pengane står på klientkonto.")


@app.post("/h/{hid}/{rolle}/{token}/salsmelding")
def salsmelding(hid: str, rolle: str, token: str):
    h = _last(hid, rolle, token)
    flyt.send_salsmelding(h, rolle)
    lager.lagre(h)
    return tilbake(h, rolle, "Salsmeldinga er sendt.")


@app.post("/h/{hid}/{rolle}/{token}/salsmelding/stadfest")
def salsmelding_stadfest(hid: str, rolle: str, token: str):
    h = _last(hid, rolle, token)
    flyt.stadfest_salsmelding(h, rolle)
    lager.lagre(h)
    return tilbake(h, rolle, "Eigarskiftet er gjennomført og pengane er utbetalte.")


@app.post("/h/{hid}/{rolle}/{token}/forsikring")
def teikn_forsikring(hid: str, rolle: str, token: str, selskap: str = Form(...)):
    h = _last(hid, rolle, token)
    flyt.vel_forsikring(h, rolle, selskap)
    lager.lagre(h)
    return tilbake(h, rolle, f"Forsikring teikna hos {selskap}.")


@app.post("/h/{hid}/{rolle}/{token}/laan", response_class=HTMLResponse)
def laanetilbod(hid: str, rolle: str, token: str, eigenkapital: str = Form("0"), aar: str = Form("5")):
    h = _last(hid, rolle, token)
    ek = int(eigenkapital) if eigenkapital.strip().isdigit() else 0
    tilboda = flyt.laanetilbod(h, ek)
    if not tilboda:
        return tilbake(h, rolle, "Du treng ikkje lån — eigenkapitalen dekkjer kjøpet.")
    val = "".join(
        f"<option value='{mal.e(t['bank'])}'>{mal.e(t['bank'])} — {t['rente']} % — "
        f"{mal.kr(t['maanadsbelop'])}/md</option>"
        for t in tilboda
    )
    kropp = f"""<div class="kort">
<h1 style="margin-top:0">Lånetilbod</h1>
<p class="svak">For {mal.kr(tilboda[0]['hovudstol'])} over {mal.e(aar)} år.</p>
<form method="post" action="{lenke(h, rolle)}/laan/vel">
<input type="hidden" name="eigenkapital" value="{ek}">
<select name="bank">{val}</select><button>Søk om lånet</button></form>
<a class="lenkeknapp" href="{lenke(h, rolle)}">Tilbake</a></div>"""
    return mal.side("Lån", kropp)


@app.post("/h/{hid}/{rolle}/{token}/laan/vel")
def vel_laan(hid: str, rolle: str, token: str, bank: str = Form(...), eigenkapital: str = Form("0")):
    h = _last(hid, rolle, token)
    ek = int(eigenkapital) if eigenkapital.strip().isdigit() else 0
    flyt.vel_laan(h, rolle, bank, ek)
    lager.lagre(h)
    return tilbake(h, rolle, f"Lånet er førehandsgodkjent hos {bank}.")


@app.post("/h/{hid}/{rolle}/{token}/avbryt")
def avbryt(hid: str, rolle: str, token: str, grunn: str = Form("")):
    h = _last(hid, rolle, token)
    flyt.avbryt(h, rolle, grunn)
    lager.lagre(h)
    return tilbake(h, rolle, "Handelen er avbroten.")


@app.get("/h/{hid}/{rolle}/{token}/kontrakt", response_class=HTMLResponse)
def vis_kontrakt(hid: str, rolle: str, token: str):
    h = lager.hent_med_token(hid, rolle, token)
    merke = (
        "<span class='merke'>Signert av begge</span>"
        if h.begge_har_signert
        else "<span class='svak'>Utkast — ikkje signert av begge</span>"
    )
    kropp = (
        f"<div class='kort tett'>{merke}<p class='svak' style='margin:8px 0 0'>"
        f"Fingeravtrykk: {mal.e(kontrakt.fingeravtrykk(h)[:24])}…</p></div>"
        f"<pre class='kontrakt'>{mal.e(kontrakt.tekst(h))}</pre>"
        f"<a class='lenkeknapp' href='{lenke(h, rolle)}'>Tilbake til handelen</a>"
    )
    return mal.side("Kontrakt", kropp)


# --- API ------------------------------------------------------------------


@app.get("/api/kjoretoy/{skilt}")
def api_kjoretoy(skilt: str):
    from .modell import normaliser_skilt

    return JSONResponse(kjoretoy.hent(normaliser_skilt(skilt)))


@app.get("/api/handel/{hid}/{rolle}/{token}")
def api_handel(hid: str, rolle: str, token: str):
    h = lager.hent_med_token(hid, rolle, token)
    d = h.til_dict()
    d["neste"] = flyt.neste_steg_tekst(h, rolle)
    d["totalt_aa_betale"] = h.totalt_aa_betale
    return JSONResponse(d)


@app.get("/helse")
def helse():
    return {"status": "oppe", "gebyr": GEBYR_KRONER, "betalingar": betalingsteneste.VENTAR}
