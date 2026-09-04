"""Vassmerke på delte videoar.

Vassmerket er ikkje pynt - det er annonsen din. Ein video som blir delt
utan merke er ei gratis levering til nokon andre sin feed. Difor er
regelen her FEILAR LUKKA: klarer vi ikkje å merke videoen, deler vi han
ikkje. Ein udelt video kostar deg ei visning; ein umerkt kostar deg
kanalen.

Krev ffmpeg. Er han ikkje installert, seier `tilgjengeleg()` nei, og
delinga skal skru seg av i staden for å sende ut umerkte filer.
"""

import logging
import shutil
import subprocess

log = logging.getLogger(__name__)

FFMPEG = "ffmpeg"
TIDSGRENSE = 120

# Nede til høgre, med litt luft. Same plass kvar gong - folk skal
# kjenne att merket, ikkje leite etter det.
PLASSERING = "x=w-tw-24:y=h-th-24"


class VassmerkeFeil(Exception):
    pass


def tilgjengeleg():
    """Har vi ffmpeg? Er svaret nei, skal deling vere av."""
    return shutil.which(FFMPEG) is not None


def bygg_kommando(inn, ut, tekst="videoapp.no", storleik=28,
                  gjennomsikt=0.75):
    """Kommandoen som brenner merket inn i videoen.

    Vi brenner det inn i biletet i staden for å leggje det som eit
    overlegg-spor. Eit spor kan strippast med eitt kommandolinjekall;
    innbrent tekst må nokon faktisk redigere bort.
    """
    if not inn or not ut:
        raise VassmerkeFeil("Manglar inn- eller utfil")
    if not 0 <= gjennomsikt <= 1:
        raise VassmerkeFeil(f"Gjennomsikt må vere 0-1, fekk {gjennomsikt}")

    # Kolon og apostrof har eiga tyding i drawtext-filteret. Slepp dei
    # gjennom urørte, og ein brukar med rett namn kan skrive sitt eige
    # filter inn i kommandoen vår.
    trygg = (str(tekst).replace("\\", "\\\\").replace(":", r"\:")
             .replace("'", r"\'").replace("%", r"\%"))

    filter_ = (f"drawtext=text='{trygg}':fontcolor=white@{gjennomsikt}"
               f":fontsize={storleik}:shadowcolor=black@0.4:shadowx=2"
               f":shadowy=2:{PLASSERING}")

    return [FFMPEG, "-y", "-i", str(inn), "-vf", filter_,
            "-codec:a", "copy", "-movflags", "+faststart", str(ut)]


def merk(inn, ut, tekst="videoapp.no", **kw):
    """Merk ein video. Kastar VassmerkeFeil om det ikkje gjekk.

    Den som kallar skal la feilen boble opp og la vere å dele videoen -
    ikkje svelgje han og sende ut fila umerkt.
    """
    if not tilgjengeleg():
        raise VassmerkeFeil(
            "ffmpeg er ikkje installert. Deling må vere av til han er det.")

    kommando = bygg_kommando(inn, ut, tekst, **kw)
    try:
        r = subprocess.run(kommando, capture_output=True, timeout=TIDSGRENSE)
    except subprocess.TimeoutExpired:
        raise VassmerkeFeil(f"ffmpeg brukte meir enn {TIDSGRENSE}s") from None
    except OSError as e:
        raise VassmerkeFeil(f"Klarte ikkje køyre ffmpeg: {e}") from e

    if r.returncode != 0:
        hale = r.stderr.decode("utf-8", "replace")[-400:]
        raise VassmerkeFeil(f"ffmpeg feila ({r.returncode}): {hale}")
    return ut
