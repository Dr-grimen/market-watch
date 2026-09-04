"""HTML-en. Éi fil, ingen byggjesteg, ingen JavaScript-rammeverk.

Grensesnittet er laga for telefon i hand, ståande, med tommelen nede: eitt
spørsmål om gongen, ein tydeleg knapp, og alltid synleg kvar i handelen du er.
Alt anna er detaljar som kan hentast fram om nokon vil sjå dei.
"""

from __future__ import annotations

import html

from .modell import REKKJEFOLGJE, STEGNAMN, Handel, Steg

CSS = """
*{box-sizing:border-box}
:root{
  --botn:#f6f6f4; --kort:#fff; --tekst:#1b1b19; --svak:#6b6b66; --kant:#e3e3de;
  --merk:#0f5c4a; --merk-tekst:#fff; --aatvar:#8a3b12; --aatvar-botn:#fdf1e7;
  --god:#1a6b3c; --god-botn:#e9f5ee;
}
@media (prefers-color-scheme:dark){:root{
  --botn:#14140f; --kort:#1e1e1a; --tekst:#f0efe9; --svak:#a3a29a; --kant:#33332c;
  --merk:#3fbf9a; --merk-tekst:#0b1a16; --aatvar:#f0b483; --aatvar-botn:#2a1c11;
  --god:#7fd6a3; --god-botn:#14261b;
}}
body{margin:0;background:var(--botn);color:var(--tekst);
  font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.ramme{max-width:560px;margin:0 auto;padding:16px 16px 64px}
header{display:flex;align-items:center;gap:10px;padding:18px 0 8px}
header .logo{width:30px;height:30px;border-radius:9px;background:var(--merk);
  color:var(--merk-tekst);display:grid;place-items:center;font-weight:700;font-size:15px}
header b{font-size:17px;letter-spacing:-.01em}
header span{color:var(--svak);font-size:13px}
h1{font-size:26px;line-height:1.2;letter-spacing:-.02em;margin:18px 0 8px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--svak);
  margin:26px 0 10px;font-weight:600}
p{margin:0 0 12px}
.svak{color:var(--svak);font-size:14px}
.kort{background:var(--kort);border:1px solid var(--kant);border-radius:14px;
  padding:16px;margin:0 0 14px}
.kort.tett{padding:12px 14px}
.rad{display:flex;justify-content:space-between;gap:12px;padding:7px 0;
  border-bottom:1px solid var(--kant);font-size:15px}
.rad:last-child{border-bottom:0}
.rad span:first-child{color:var(--svak)}
.rad span:last-child{text-align:right;font-variant-numeric:tabular-nums}
.sum{font-weight:700;font-size:17px}
label{display:block;font-size:13px;color:var(--svak);margin:12px 0 4px}
input,textarea,select{width:100%;padding:12px;border:1px solid var(--kant);
  border-radius:10px;background:var(--botn);color:var(--tekst);font-size:16px}
textarea{min-height:70px;font-family:inherit}
button{width:100%;padding:14px;border:0;border-radius:12px;background:var(--merk);
  color:var(--merk-tekst);font-size:16px;font-weight:600;margin-top:16px;cursor:pointer}
button.mild{background:transparent;color:var(--svak);border:1px solid var(--kant);
  font-weight:500;margin-top:8px}
a{color:var(--merk)}
.lenkeknapp{display:block;text-align:center;padding:13px;border:1px solid var(--kant);
  border-radius:12px;text-decoration:none;margin-top:8px;color:var(--tekst)}
.stig{display:flex;gap:4px;margin:4px 0 18px}
.stig div{flex:1;height:4px;border-radius:2px;background:var(--kant)}
.stig div.gjort{background:var(--merk)}
.merke{display:inline-block;font-size:12px;padding:3px 9px;border-radius:99px;
  background:var(--god-botn);color:var(--god);font-weight:600}
.aatvaring{background:var(--aatvar-botn);color:var(--aatvar);border-radius:12px;
  padding:12px 14px;margin:0 0 12px;font-size:14px}
.feil{background:var(--aatvar-botn);color:var(--aatvar);border-radius:12px;
  padding:12px 14px;margin:0 0 14px;font-size:15px}
.god{background:var(--god-botn);color:var(--god);border-radius:12px;
  padding:12px 14px;margin:0 0 14px;font-size:15px}
.kode{font-size:30px;letter-spacing:.16em;font-weight:700;text-align:center;
  padding:14px 0;font-variant-numeric:tabular-nums}
.logg{list-style:none;padding:0;margin:0;font-size:14px}
.logg li{padding:8px 0 8px 16px;border-left:2px solid var(--kant);position:relative}
.logg li::before{content:"";position:absolute;left:-5px;top:14px;width:8px;height:8px;
  border-radius:50%;background:var(--kant)}
.logg li:first-child::before{background:var(--merk)}
pre.kontrakt{white-space:pre-wrap;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--kort);border:1px solid var(--kant);border-radius:14px;padding:16px}
footer{color:var(--svak);font-size:12px;text-align:center;padding:28px 0 8px}
"""


def e(t) -> str:
    return html.escape(str(t if t is not None else ""))


def kr(tal) -> str:
    return f"{int(tal or 0):,}".replace(",", " ") + " kr"


def side(tittel: str, kropp: str, melding: str = "", feil: str = "") -> str:
    varsel = ""
    if feil:
        varsel += f'<div class="feil">{e(feil)}</div>'
    if melding:
        varsel += f'<div class="god">{e(melding)}</div>'
    return f"""<!doctype html>
<html lang="nn"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0f5c4a">
<title>{e(tittel)} · Bruktbil</title>
<style>{CSS}</style>
</head><body><div class="ramme">
<header><div class="logo">B</div><div><b>Bruktbil</b><br>
<span>heile handelen på éin stad</span></div></header>
{varsel}{kropp}
<footer>Demo. BankID, betaling og eigarskifte er simulerte.</footer>
</div></body></html>"""


def stig(h: Handel) -> str:
    if h.steg == Steg.AVBROTEN.value:
        return '<div class="stig"></div>'
    naa = REKKJEFOLGJE.index(Steg(h.steg))
    boksar = "".join(
        f'<div class="{"gjort" if i <= naa else ""}"></div>'
        for i in range(len(REKKJEFOLGJE))
    )
    return f'<div class="stig">{boksar}</div><p class="svak">Steg {naa + 1} av ' \
           f'{len(REKKJEFOLGJE)} — {e(STEGNAMN[Steg(h.steg)])}</p>'


def bilkort(h: Handel) -> str:
    b = h.bil or {}
    radene = [
        ("Skiltnummer", b.get("skilt", "")),
        ("Årsmodell", b.get("aarsmodell", "")),
        ("Kilometerstand", f"{b.get('kilometerstand', 0):,}".replace(",", " ") + " km"),
        ("Drivstoff", b.get("drivstoff", "")),
        ("Girkasse", b.get("girkasse", "")),
        ("EU-kontroll", b.get("eu_kontroll_frist", "")),
    ]
    inni = "".join(f"<div class='rad'><span>{e(k)}</span><span>{e(v)}</span></div>" for k, v in radene)
    aatvaringar = "".join(f"<div class='aatvaring'>{e(m)}</div>" for m in b.get("merknader", []))
    return f"""<div class="kort">
<h1 style="margin-top:0">{e(b.get('merke',''))} {e(b.get('modell',''))}</h1>
<p class="svak">Kjelde: {e(b.get('kjelde',''))}</p>
{inni}</div>{aatvaringar}"""


def prisrad(h: Handel) -> str:
    return f"""<div class="kort">
<div class="rad"><span>Kjøpesum</span><span>{kr(h.pris)}</span></div>
<div class="rad"><span>Omregistrering (estimat)</span><span>{kr(h.omregistreringsavgift)}</span></div>
<div class="rad"><span>Gebyr for tenesta</span><span>{kr(199)}</span></div>
<div class="rad sum"><span>Kjøparen betaler</span><span>{kr(h.totalt_aa_betale)}</span></div>
</div>"""


def logg(h: Handel) -> str:
    if not h.logg:
        return ""
    element = "".join(
        f"<li><b>{e(x['tekst'])}</b><br><span class='svak'>{e(x['tid'][:16].replace('T',' '))}</span></li>"
        for x in reversed(h.logg[-12:])
    )
    return f"<h2>Det som har skjedd</h2><ul class='logg'>{element}</ul>"
