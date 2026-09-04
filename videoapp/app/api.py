"""HTTP-laget. Tynt med vilje - all logikken ligg under.

Fire endepunkt er alt appen treng:

  POST /video          bestill ein video     -> jobb_id
  GET  /video/{id}     kor langt er han      -> status + plass i kø
  GET  /saldo/{brukar} kor mange kredittar   -> tal
  GET  /helse          går rekneskapen opp?  -> for overvaking

Merk at bestilling svarar med ein gong og ALDRI ventar på videoen.
Det er ikkje latskap - det er den einaste måten dette skalerer. Ein
generering tek eit minutt; held du HTTP-tilkoplinga open imens, klarer
du nokre hundre samtidige brukarar. Slepper du henne, klarer du
millionar, og køen bestemmer farten.

Autentisering er IKKJE med her. Brukar-id kjem frå ein header, og det
er openbert utrygt. Set ekte token-validering framfor dette før
lansering - sjå merknaden ved _brukar().
"""

import logging

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .jobb import AVVIST, FOR_LITE

log = logging.getLogger(__name__)


class Tinging(BaseModel):
    bilde_url: str = Field(min_length=1, max_length=2000)
    onske: str = Field(min_length=1, max_length=500)
    nivaa: str = "standard"
    idem: str | None = Field(default=None, max_length=200)


def lag_app(bestilling, ko, ledger, prisbok):
    app = FastAPI(title="videoapp")

    def _brukar(x_brukar_id: str = Header(default="")):
        # MIDLERTIDIG. Dette stolar på ein header, som kven som helst
        # kan setje. Bytt til validering av eit signert token før
        # lansering, elles kan kven som helst bruke andre sine kredittar.
        if not x_brukar_id:
            raise HTTPException(401, "Manglar X-Brukar-Id")
        return x_brukar_id

    @app.post("/video", status_code=202)
    def bestill(t: Tinging, brukar: str = Depends(_brukar)):
        if t.nivaa not in prisbok.nivaa:
            raise HTTPException(400, f"Ukjent nivå: {t.nivaa}")

        jobb_id, utfall = bestilling.bestill(
            brukar, t.bilde_url, t.onske, t.nivaa, idem=t.idem)

        if utfall.status == AVVIST:
            # 422, ikkje 500. Dette er eit gyldig svar på ei ugyldig
            # tinging, og appen skal vise grunnen til brukaren.
            raise HTTPException(422, utfall.grunn)
        if utfall.status == FOR_LITE:
            # 402 Payment Required. Appen viser kjøpsskjermen på denne.
            raise HTTPException(402, "Ikkje nok kredittar")

        return {"jobb_id": jobb_id, "status": "i_ko",
                "plass_i_ko": ko.plass_i_ko(jobb_id),
                "kredittar_att": ledger.saldo(brukar)}

    @app.get("/video/{jobb_id}")
    def status(jobb_id: str, brukar: str = Depends(_brukar)):
        rad = ko.status(jobb_id)
        if rad is None or rad["brukar"] != brukar:
            # Same svar på "finst ikkje" og "ikkje din", så ingen kan
            # kartleggje kva jobbar som finst.
            raise HTTPException(404, "Ukjend jobb")
        return {
            "jobb_id": jobb_id,
            "status": rad["status"],
            "video_url": rad["video_url"],
            "plass_i_ko": ko.plass_i_ko(jobb_id),
            "grunn": rad["grunn"],
        }

    @app.get("/saldo/{brukar_id}")
    def saldo(brukar_id: str, brukar: str = Depends(_brukar)):
        if brukar_id != brukar:
            raise HTTPException(403, "Ikkje din saldo")
        return {"kredittar": ledger.saldo(brukar),
                "reservert": ledger.reservert(brukar)}

    @app.get("/helse")
    def helse():
        """Går kredittrekneskapen opp? Overvak denne.

        Svarar han nei, har du ein bug som lagar eller øydelegg
        kredittar. Det er ein alarm, ikkje ein logglinje.
        """
        ok = ledger.stemmer()
        return {"ok": ok, "ko": ko.tal()}

    return app
