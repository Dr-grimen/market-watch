"""MiniMax Hailuo.

MERK: MiniMax er asynkron - du sender inn, får ein task_id, og pollar.
Endepunkta og feltnamna under er slik dei såg ut då dette blei skrive.
Sjekk dei mot gjeldande API-dokumentasjon før produksjon; MiniMax har
endra både vertsnamn og feltnamn før.

MERK OGSÅ: MiniMax ligg utanfor EØS. Sender du brukarbilde med ansikt
hit, er det ei overføring av persondata etter GDPR kapittel V og må ha
eit rettsleg grunnlag. Sjå README.
"""

import time

import requests

from .base import Jobb, Leverandor, MellombelsFeil, Resultat, VarigFeil

BASIS = "https://api.minimax.io/v1"

# Feil som tyder "prøv ein annan", ikkje "gi opp".
MELLOMBELS_KODER = {429, 500, 502, 503, 504}


class MiniMax(Leverandor):
    nokkel = "minimax"

    def __init__(self, konfig, api_nokkel=None, modell=None, timeout=300):
        super().__init__(konfig, api_nokkel)
        self.modell = modell or "MiniMax-Hailuo-02"
        self.timeout = timeout

    def generer(self, jobb):
        task_id = self._send(jobb)
        fil_id = self._vent(task_id)
        url = self._hent_url(fil_id)
        return Resultat(
            video_url=url,
            leverandor=self.konfig.nokkel,
            sekund=jobb.sekund,
            kostnad_nok=self.konfig.usd_per_second * jobb.sekund * self._nok_per_usd,
        )

    # Blir sett av ruteren, som kjenner valutakursen frå prisboka.
    _nok_per_usd = 10.5

    def _send(self, jobb):
        kropp = {
            "model": self.modell,
            "prompt": jobb.prompt,
            "duration": jobb.sekund,
            "resolution": self.konfig.api_opplosning(jobb.boette),
        }
        if jobb.modus == "bilde_til_video":
            kropp["first_frame_image"] = jobb.bilde_url

        data = self._kall("POST", "/video_generation", json=kropp)
        task_id = data.get("task_id")
        if not task_id:
            raise VarigFeil(f"MiniMax gav ingen task_id: {data}")
        return task_id

    def _vent(self, task_id):
        frist = time.time() + self.timeout
        pause = 3
        while time.time() < frist:
            data = self._kall("GET", "/query/video_generation",
                              params={"task_id": task_id})
            status = data.get("status")
            if status == "Success":
                fil_id = data.get("file_id")
                if not fil_id:
                    raise VarigFeil(f"Ferdig, men ingen file_id: {data}")
                return fil_id
            if status == "Fail":
                # Feila jobben på innhaldet, hjelper det ikkje å prøve
                # same jobben ein annan stad.
                raise VarigFeil(f"MiniMax avviste jobben: {data}")
            time.sleep(pause)
            pause = min(pause * 1.5, 15)
        raise MellombelsFeil(f"MiniMax brukte meir enn {self.timeout}s")

    def _hent_url(self, fil_id):
        data = self._kall("GET", "/files/retrieve", params={"file_id": fil_id})
        url = (data.get("file") or {}).get("download_url")
        if not url:
            raise VarigFeil(f"Ingen download_url: {data}")
        return url

    def _kall(self, metode, sti, **kw):
        try:
            svar = requests.request(
                metode, BASIS + sti,
                headers={"Authorization": f"Bearer {self.api_nokkel}"},
                timeout=60, **kw)
        except requests.Timeout as e:
            raise MellombelsFeil(f"Timeout mot MiniMax: {e}") from e
        except requests.RequestException as e:
            raise MellombelsFeil(f"Nettverksfeil mot MiniMax: {e}") from e

        if svar.status_code in MELLOMBELS_KODER:
            raise MellombelsFeil(f"MiniMax {svar.status_code}: {svar.text[:200]}")
        if svar.status_code >= 400:
            raise VarigFeil(f"MiniMax {svar.status_code}: {svar.text[:200]}")

        data = svar.json()
        # MiniMax legg den verkelege feilen i base_resp, ikkje i HTTP-koden.
        basis = data.get("base_resp") or {}
        kode = basis.get("status_code", 0)
        if kode not in (0, None):
            melding = basis.get("status_msg", "")
            if kode in (1002, 1039):        # rate limit / for mange kall
                raise MellombelsFeil(f"MiniMax {kode}: {melding}")
            raise VarigFeil(f"MiniMax {kode}: {melding}")
        return data
