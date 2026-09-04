"""Portvakta. Apple slepp deg ikkje inn utan denne.

Ein viktig skilnad frå resten av koden: promptforbetringa feilar OPE -
går ho ned, lagar vi videoen likevel. Moderering feilar LUKKA. Kan vi
ikkje sjekke innhaldet, lagar vi ingenting.

Grunnen er asymmetrien i kva ein feil kostar. Ein dårleg prompt gir ein
kjedeleg video. Eit bilde som slepp gjennom kan koste deg appen, og i
verste fall vere ei straffesak.

Fire ting vi ikkje lagar video av:

  barn        - biletmateriale med mindreårige i seksualisert samanheng.
                Dette er den einaste kategorien der du har ei aktiv
                plikt: mistanke skal meldast til politiet, ikkje berre
                blokkerast. Sjå MELDEPLIKT nedanfor.
  verkeleg    - namngjevne, gjenkjennelege verkelege personar. Deepfake
                av naboen er det som gir deg medieoppslag og sokseamaal.
  seksuelt    - Apple sin retningslinje 1.1.4. Ikkje forhandlingsbart.
  ulovleg     - vaapen, narkotika, vald som instruksjon.

Alt blir logga. Du treng loggen naar Apple spor, naar politiet spor, og
naar ein brukar klagar paa at han blei stoppa.
"""

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

MODELLAR = ["claude-haiku-4-5", "claude-sonnet-5"]
MAKS_UT = 200

# MELDEPLIKT: treff i denne kategorien skal ikkje berre blokkerast.
# Norsk rett palegg deg aa melde frae. Kripos tek imot pa
# https://tips.kripos.no - avklar rutinen med advokat foer lansering.
MELDEPLIKTIG = {"barn"}

KATEGORIAR = ("barn", "verkeleg", "seksuelt", "ulovleg")

SYSTEM = """Du er innhaldsfilter for ein app som lagar korte videoar frå
bilde brukarar lastar opp.

Du får ein prompt, og av og til eit bilde. Avgjer om vi skal lage videoen.

Avvis dersom noko av dette gjeld:

- barn: mindreårige i seksualisert eller upassande samanheng
- verkeleg: ein namngjeven eller openbert gjenkjenneleg verkeleg person
  (politikarar, kjendisar, offentlege personar). Brukaren sitt eige
  bilde av seg sjølv eller familien er GREITT - det er kjendisar og
  namngjevne personar som er problemet.
- seksuelt: seksuelt innhald eller nakenheit
- ulovleg: våpenbruk, narkotika, vald som instruksjon, sjølvskading

Vanlege ting skal sleppe gjennom. Eit bilde av ein katt som skal danse
er greitt. Eit portrett av brukaren sjølv som skal smile er greitt. Ver
ikkje overivrig - falske avslag gjer at folk sluttar å bruke appen.

Svar med JSON og ingenting anna:
{"ok": true}
eller
{"ok": false, "kategori": "<ein av: barn, verkeleg, seksuelt, ulovleg>",
 "grunn": "<kort forklaring til brukaren, på norsk>"}"""


@dataclass(frozen=True)
class Vurdering:
    ok: bool
    kategori: str = ""
    grunn: str = ""
    meldepliktig: bool = False
    # True når vi avviste fordi filteret var nede, ikkje fordi innhaldet
    # var gale. Desse skal du telje - mange av dei tyder driftsproblem,
    # ikkje at brukarane dine har blitt verre.
    usikker: bool = False


GODKJENT = Vurdering(ok=True)


class Moderering:
    def __init__(self, api_nokkel=None, klient=None, logg_sti=None):
        self._klient = klient
        self._api_nokkel = api_nokkel
        self.logg_sti = Path(logg_sti) if logg_sti else None

    @property
    def klient(self):
        if self._klient is None:
            self._klient = (
                anthropic.Anthropic(api_key=self._api_nokkel)
                if self._api_nokkel else anthropic.Anthropic())
        return self._klient

    def sjekk(self, prompt, bilde_b64=None, bilde_type="image/jpeg",
              brukar=None):
        """Skal vi lage denne videoen?

        Returnerer alltid ei Vurdering. Feilar noko, blir svaret nei -
        aldri eit ja vi ikkje har dekning for.
        """
        innhald = []
        if bilde_b64:
            innhald.append({
                "type": "image",
                "source": {"type": "base64", "media_type": bilde_type,
                           "data": bilde_b64},
            })
        innhald.append({"type": "text", "text": f"Prompt: {prompt}"})

        vurdering = self._spor(innhald)
        self._logg(brukar, prompt, vurdering, hadde_bilde=bool(bilde_b64))
        return vurdering

    def _spor(self, innhald):
        for modell in MODELLAR:
            try:
                svar = self.klient.messages.create(
                    model=modell,
                    max_tokens=MAKS_UT,
                    system=SYSTEM,
                    messages=[{"role": "user", "content": innhald}],
                )
            except anthropic.APIStatusError as e:
                if e.status_code == 404:
                    continue
                log.warning("Moderering: API-feil %s frå %s", e.status_code,
                            modell)
                continue
            except Exception as e:                  # noqa: BLE001
                log.warning("Moderering: %s feila: %s", modell, e)
                continue

            tekst = "".join(
                b.text for b in svar.content
                if getattr(b, "type", "") == "text").strip()
            vurdering = self._tolk(tekst)
            if vurdering is not None:
                return vurdering
            log.warning("Moderering: kunne ikkje tolke svar frå %s", modell)

        # Ingen modell svarte brukbart. Vi seier nei.
        log.error("Moderering utilgjengeleg - avviser for sikkerheits skuld")
        return Vurdering(
            ok=False, kategori="", usikker=True,
            grunn="Vi klarte ikkje å sjekke innhaldet no. Prøv igjen om litt.")

    def _tolk(self, tekst):
        tekst = tekst.strip()
        if tekst.startswith("```"):
            tekst = tekst.strip("`")
            tekst = tekst.split("\n", 1)[-1] if "\n" in tekst else tekst
        start, slutt = tekst.find("{"), tekst.rfind("}")
        if start < 0 or slutt <= start:
            return None
        try:
            d = json.loads(tekst[start:slutt + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(d, dict) or "ok" not in d:
            return None

        if d["ok"] is True:
            return GODKJENT

        kategori = str(d.get("kategori", "")).strip().lower()
        if kategori not in KATEGORIAR:
            # Modellen sa nei, men med ein kategori vi ikkje kjenner.
            # Vi stolar på neiet, ikkje på kategorien.
            kategori = ""
        return Vurdering(
            ok=False,
            kategori=kategori,
            grunn=str(d.get("grunn", "Innhaldet kan vi ikkje lage video av."))[:300],
            meldepliktig=kategori in MELDEPLIKTIG,
        )

    def _logg(self, brukar, prompt, vurdering, hadde_bilde):
        """Skriv avgjerda til fil. Du treng denne når nokon spør.

        Vi loggar ikkje sjølve biletet - berre at det var eitt. Å lagre
        avvist biletmateriale skaper eit større problem enn det løyser.
        """
        if vurdering.ok and not self.logg_sti:
            return
        rad = {
            "tid": time.time(),
            "brukar": brukar,
            "prompt": prompt[:300],
            "hadde_bilde": hadde_bilde,
            **asdict(vurdering),
        }
        if vurdering.meldepliktig:
            log.critical("MELDEPLIKTIG TREFF - brukar=%s. Sjå tips.kripos.no",
                         brukar)
        elif not vurdering.ok:
            log.info("Avvist (%s) for brukar=%s", vurdering.kategori or "?",
                     brukar)

        if self.logg_sti:
            self.logg_sti.parent.mkdir(parents=True, exist_ok=True)
            with self.logg_sti.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rad, ensure_ascii=False) + "\n")
