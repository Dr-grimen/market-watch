# Bruktbil

Heile bruktbilhandelen mellom to privatpersonar i éin flyt: oppslag på skiltet,
kontrakt, BankID-signering, oppgjer over klientkonto, eigarskifte hos
Vegvesenet — og forsikring og lån på vegen.

**199 kr for handelen.** NAF tek 89 kr for berre kontrakten. Resten av jobben —
oppslaget, oppgjeret, eigarskiftet, uvissa — må folk ordne sjølve i dag.

---

## Kvifor dette er verdt å byggje

Det blir seld rundt **500 000 bruktbilar i Noreg i året**, og størstedelen av
privatsala går føre seg med kontrakt frå ein PDF, pengar over Vipps eller
bankoverføring, og to menneske som må stole på kvarandre utan å ha noko å halde
seg til om det går gale.

Éin flyt til 199 kr treffer eit marked på nokre hundre millionar kroner i året
— men berre viss appen faktisk tek bort risikoen, ikkje berre papiret. Difor er
klientkontoen kjernen i produktet, ikkje kontrakten.

---

## Slik verkar det

```
Seljar skriv skiltnummer  ─►  oppslag: bil, heftingar, EU-kontroll, merknader
        │
        ├─►  delingskode  ─►  kjøparen blir med (BankID)
        │
   vilkåra: pris, km, utstyr, kjende feil, overlevering
        │
   kontrakten blir laga av dei same tala begge har sett
        │
   BankID-signering  ─►  begge signerer same tekst, låst med fingeravtrykk
        │
   kjøparen betaler til KLIENTKONTO  ─►  pengane står trygt, ingen har dei
        │
   seljaren sender salsmelding  ─►  kjøparen stadfestar
        │
   eigarskiftet er gjennomført  ─►  pengane blir utbetalte same augeblink
```

Regelen som ber heile appen: **ingen ting går bakover, og ingen steg kan hoppast
over.** Ein kan ikkje betale før begge har signert, ikkje melde eigarskifte før
pengane er inne, og ikkje få utbetalt før bilen står i kjøparen sitt namn.

---

## Kom i gang

```bash
cd bruktbil
./kjor.sh                  # http://localhost:8000
```

Eller sjå heile handelen renne gjennom i terminalen:

```bash
python3 demo.py            # skilt som argument om du vil: python3 demo.py EL45678
python3 -m unittest discover -s testar -t .
```

Demo-skilt med ferdige data: **DB12345** (Golf) og **EL45678** (Tesla med pant
frå Santander, som gir merknad i appen og eigen linje i kontrakten). Alle andre
skilt gir oppdikta, men konsekvente data.

---

## Kva som er ekte og kva som er simulert

Alt som handlar om *korleis handelen heng saman* er ekte kode: rekkjefølgja,
reglane, kontrakten, valideringa, pengeflyten, fingeravtrykket på signaturane.

Alt som krev ein avtale med nokon andre er ein **port** i `app/tenester/` — ei
lita fil med eit tydeleg grensesnitt og eit demo-svar bak:

| Port | I dag | I drift |
|---|---|---|
| `kjoretoy.py` | demoregister + oppdikta data | Statens vegvesen, kjøretøyopplysningar + heftingar |
| `bankid.py` | kode på skjermen | Signicat / Vipps BankID / Criipto |
| `betaling.py` | ordbok i minnet | klientmiddelkonto i bank eller betalingsføretak |
| `eigarskifte.py` | ordbok i minnet | Vegvesenet: salsmelding og omregistrering |
| `forsikring.py` | rekna pris | prisspørjing mot selskapa |
| `laan.py` | annuitet med reelle satsar | søknad til bankane |
| `finn.py` | to demo-annonsar | annonseoppslag der vi har løyve |

Å byte ut ein av dei er å skrive om innmaten i éi fil. Resten av appen merkar
det ikkje. `testar/` går like grønt før og etter.

> Merk: `betaling` og `eigarskifte` held demo-tilstanden i minnet. Startar du
> tenaren på nytt midt i ein handel, finst ikkje betalings-ID-en lenger. Ekte
> leverandørar har eigen database og eige webhook — det problemet forsvinn med
> den første integrasjonen.

---

## Filene

```
app/
  modell.py     handelen som datastruktur + validering (fnr og kontonr med mod11)
  flyt.py       alle reglane. Kva som er lov når, og kva som skjer då.
  kontrakt.py   kontrakten, og fingeravtrykket signaturane festar seg til
  lager.py      SQLite. Éin handel = éi rad.
  web.py        rutene. Hentar handel, kallar flyt, teiknar side.
  mal.py        HTML og CSS. Mobilfyrst, ingen JavaScript.
  tenester/     portane mot verda utanfor
testar/         29 testar: heile flyten, alle måtane han kan misbrukast
demo.py         heile handelen i terminalen
```

---

## Det testane passar på

Dei viktigaste er ikkje at flyten går gjennom, men at snarvegane er stengde:

- pengar kan ikkje krevjast før begge har signert
- eigarskifte kan ikkje meldast før pengane står på klientkonto
- seljaren kan ikkje stadfeste si eiga salsmelding
- prisen kan ikkje endrast etter at nokon har signert
- **blir kontrakten endra etter signering, blir det oppdaga** (fingeravtrykk)
- fødselsnummer står aldri i klartekst, korkje i kontrakten eller i databasen
- feil BankID-kode signerer ingen ting
- lenka til den eine parten opnar ikkje handelen til den andre

Ein av dei testane fann ein ekte feil under bygginga: kontrakten endra seg
mellom den første og den andre signaturen, fordi identiteten blei fylt inn
undervegs. No blir begge partar identifiserte *før* teksten blir skriven — slik
det uansett fungerer med ekte BankID-innlogging.

---

## Vidare

`APPSTORE.md` går gjennom kva som skal til for å få dette i App Store: kva Apple
krev, kva Finanstilsynet krev, kva avtalar som må på plass, og kvifor gebyret
på 199 kr slepp unna Apple sine 30 %.
