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

Brukar-id kjem frå eit signert token i Authorization-headeren, ikkje
frå ein header klienten kan finne på sjølv. Sjå app/auth.py.
"""

import logging

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .auth import AuthFeil, les_token
from .jobb import AVVIST, FOR_LITE, USIKKER

log = logging.getLogger(__name__)


class Tinging(BaseModel):
    bilde_url: str = Field(min_length=1, max_length=2000)
    onske: str = Field(min_length=1, max_length=500)
    nivaa: str = "standard"
    idem: str | None = Field(default=None, max_length=200)


def lag_app(bestilling, ko, ledger, prisbok, token_nokkel=None):
    app = FastAPI(title="videoapp")

    def _brukar(authorization: str = Header(default="")):
        """Brukar-id frå eit signert token. Feilar lukka.

        Alle avvisingar gir same svar. Skil du mellom "manglar token",
        "utgått" og "feil signatur", fortel du ein angripar kva han
        skal justere.
        """
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Ugyldig token")
        try:
            return les_token(authorization[7:], token_nokkel)
        except AuthFeil:
            raise HTTPException(401, "Ugyldig token") from None

    @app.post("/video", status_code=202)
    def bestill(t: Tinging, brukar: str = Depends(_brukar)):
        if t.nivaa not in prisbok.nivaa:
            raise HTTPException(400, f"Ukjent nivå: {t.nivaa}")

        jobb_id, utfall = bestilling.bestill(
            brukar, t.bilde_url, t.onske, t.nivaa, idem=t.idem)

        if utfall.status == USIKKER:
            # 503, ikkje 422. Moderatoren vaar er nede - det er ikkje
            # brukaren sitt innhald som er problemet, og appen skal be
            # han prove igjen i staden for aa seie at han gjorde noko gale.
            raise HTTPException(503, utfall.grunn)
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

    @app.get("/saldo")
    def saldo(brukar: str = Depends(_brukar)):
        """Ingen brukar-id i stien - tokenet seier kven du er.

        Tek du id-en frå stien, må du hugse å sjekke at han stemmer med
        tokenet kvar einaste gong. Tek du han frå tokenet, kan du ikkje
        gløyme det.
        """
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
