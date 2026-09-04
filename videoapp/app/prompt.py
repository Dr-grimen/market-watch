"""Gjer «få han til å gå» om til noko ein videomodell forstår.

Dette er kjerna i «éin knapp». Brukaren skriv tre ord; modellen treng
kamerarørsle, lys, tempo og stil for å lage noko som ser bra ut. Vi
fyller inn resten stille.

Viktig designval: FEILAR DETTE, STOPPAR VI IKKJE VIDEOEN. Brukaren har
betalt kredittar. At omskrivaren er nede er vårt problem, ikkje deira -
då sender vi teksten deira rå og lagar ein litt dårlegare video, i
staden for ei feilmelding.

Modellval: claude-haiku-4-5. Dette er ei kort omskrivingsoppgåve som
går på kvar einaste generering, så prisen betyr meir enn djupna. Vil du
ha betre promptar, byt MODELLAR under - opus-5 er klart flinkare, men
kostar fem gonger meir per kall.
"""

import logging
import re

import anthropic

log = logging.getLogger(__name__)

# Billegast først. Same mønster som src/analyze.py i dette repoet.
MODELLAR = ["claude-haiku-4-5", "claude-sonnet-5"]

MAKS_INN = 500      # teikn frå brukaren vi tek med
MAKS_UT = 300       # ein prompt, ikkje eit essay

SYSTEM = """Du skriv om korte brukarønske til promptar for ein AI-videomodell.

Brukaren har lasta opp eit bilde og skrive nokre få ord om kva som skal
skje. Du skal skrive éin prompt som får videomodellen til å lage ein
kort, god klipp ut av det biletet.

Reglar:
- Skriv på engelsk. Videomodellane er trente på engelsk.
- Éin samanhengande setning eller to. Aldri punktliste, aldri overskrifter.
- Behald det brukaren faktisk bad om. Ikkje finn på ei anna historie.
- Legg til det brukaren ikkje tenkte på: kamerarørsle, tempo, lys.
- Hald rørsla roleg og truverdig. Brå eller stor rørsle blir stygt paa
  fem sekund.
- Ikkje nemn lyd, tale eller tekst i biletet. Modellen lagar ikkje det.
- Ikkje skriv noko om verkelege, namngjevne personar.

Svar med prompten aleine. Ingen forklaring, ingen hermeteikn."""

# Brukarteksten kan innehalde alt mogleg. Han er data, ikkje instruksjonar
# - difor ligg han i ei user-melding og aldri i systemprompten.
MAL = """Bilde: {bilde}
Brukaren skreiv: {onske}

Skriv prompten."""


def forbetre(onske, bilde_skildring="eit bilde brukaren lasta opp",
             api_nokkel=None, klient=None):
    """Returnerer ein betre prompt, eller brukaren sin eigen viss noko feilar.

    Kastar aldri. Ein video som blir litt dårlegare er alltid betre enn
    ein video som ikkje blir laga.
    """
    reinsa = _reins(onske)
    if not reinsa:
        return onske

    klient = klient or (
        anthropic.Anthropic(api_key=api_nokkel) if api_nokkel
        else anthropic.Anthropic()
    )

    for modell in MODELLAR:
        try:
            svar = klient.messages.create(
                model=modell,
                max_tokens=MAKS_UT,
                system=SYSTEM,
                messages=[{
                    "role": "user",
                    "content": MAL.format(bilde=bilde_skildring, onske=reinsa),
                }],
            )
        except anthropic.RateLimitError:
            log.warning("Rate limit på %s - prøver neste", modell)
            continue
        except anthropic.APIStatusError as e:
            if e.status_code == 404:
                log.warning("Modellen %s finst ikkje - prøver neste", modell)
                continue
            log.warning("API-feil %s frå %s", e.status_code, modell)
            continue
        except anthropic.APIConnectionError as e:
            log.warning("Nettverksfeil mot Anthropic: %s", e)
            break
        except Exception as e:                      # noqa: BLE001
            # Omskrivaren skal aldri vere grunnen til at ein betalt
            # video ikkje blir laga.
            log.exception("Uventa feil i promptforbetring: %s", e)
            break

        tekst = "".join(
            b.text for b in svar.content if getattr(b, "type", "") == "text"
        ).strip()
        if tekst:
            return _reins_svar(tekst)

    log.info("Fall tilbake til brukaren sin eigen prompt")
    return onske


def _reins(tekst):
    """Kutt lengd og fjern kontrollteikn. Ingen sensur - berre hygiene."""
    if not tekst:
        return ""
    tekst = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(tekst))
    tekst = re.sub(r"\s+", " ", tekst).strip()
    return tekst[:MAKS_INN]


def _reins_svar(tekst):
    """Modellen svarar av og til med hermeteikn eller ein liten forklaring."""
    tekst = tekst.strip().strip('"').strip("'").strip()
    # Tek første avsnitt dersom han la til noko etterpå likevel.
    return tekst.split("\n\n")[0].strip()
