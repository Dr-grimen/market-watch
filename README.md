# market-watch

Eit personleg varslingsverktøy som følgjer **Nasdaq** og **olje**, les nyheiter
frå heile verda, og sender deg **berre** melding når det er rimeleg sikkert kva veg
det ber. Er det uklart, held det kjeft. Det er heile poenget.

---

## Slik verkar det

```
Prisar (CNBC)        ─┐
46 nyheitskjelder    ─┼─► Regelfilter ──► Claude Haiku ──► Terskel ──► Telegram
7 Reddit-forum       ─┘     (gratis)      (kostar litt)    (streng)
```

1. **Hentar** prisar og ~470 saker frå 46 kjelder + 7 Reddit-forum. Parallelt, ~20 sekund.
2. **Filtrerer** vekk 97–98 % med ord-, hendings- og duplikatreglar. Kostar 0 kr.
3. **Vurderer** dei 12 som står igjen med Claude Haiku, som gir ein `confidence` mellom 0 og 1.
4. **Siler**: under terskelen i `config.yaml` → ingen melding. Uklar retning → ingen melding.
   Mistenkeleg innhald → ingen melding. Allereie varsla → ingen melding.
5. **Sender** melding på Telegram berre når alle portane er passert.

Køyrer **kvart 20. minutt** frå morgonen til natta, alle kvardagar. Er det helg
eller mellom 01 og 07, avsluttar det med ein gong utan å bruke ei krone.
Mellom 14:00 og 15:30 norsk tid skiftar verktøyet automatisk til
*før-opning-modus* og spør spesifikt: **tyder noko på at børsen opnar opp?**

To detaljar som gjer at det faktisk fungerer:

- **Kryss-kjelde-teljing.** Melder fem aviser same sak, tel det som eit styrkesignal.
  Ei einsleg overskrift veg lite.
- **Nær-duplikat-samanslåing.** «Fed's Collins says rates may rise» og «Collins:
  holding rates hangs on inflation» er same hending. Utan dette ville tre av
  tolv Claude-plassar gått til å lese den same nyheita om att.

---

## Kom i gang — éin kommando

```bash
cd ~/market-watch && ./oppsett.sh
```

Skriptet gjer alt som kan gjerast automatisk: lagar Python-miljøet, lagar `.env`,
testar Telegram, og set opp automatisk køyring kvart 20. minutt på denne Macen.

Manglar det ein nøkkel, **stoppar det og skriv ut ei steg-for-steg-oppskrift**
med nøyaktig kva du skal trykke på. Fyll inn, køyr på nytt, ferdig.

Du treng ingen GitHub-konto for dette.

### Dei to nøklane du må hente sjølv

Eg kan ikkje hente desse for deg — dei krev di innlogging og ditt kort.

**Telegram (gratis, ~3 min).** Søk opp **@BotFather** i Telegram → `/newbot` →
vel namn og eit brukarnamn som sluttar på `bot`. Du får eit token som ser slik ut:
`8123456789:AAF2h-...`. Lim det inn i `.env`. Søk så opp *ditt eige* bot, trykk
START og send `hei` — utan det får ikkje botet lov å sende til deg. Køyr til slutt:

```bash
cd ~/market-watch && ./hent-chatid.sh
```

Den les tokenet frå `.env`, spør Telegram, og skriv ut chat-ID-en din.

**Anthropic (~3 min).** https://console.anthropic.com → Billing → legg inn kort
og fyll på 5 USD (held i mange månader) → Settings → API Keys → Create Key.
Nøkkelen startar med `sk-ant-` og blir **berre vist éin gong**.

Begge limer du inn i `.env`:

```bash
open -e ~/market-watch/.env
```

Ikkje lim nøklane inn i ein chat eller i koden. Dei skal berre i `.env`, som er
i `.gitignore` og aldri følgjer med til GitHub.

---

## Køyre og teste manuelt

Sjekk oppsettet — den seier rett ut kva som manglar og testar at kjeldene svarer:

```bash
cd ~/market-watch && .venv/bin/python -m src.main --doctor
```

Når han er grøn, test at Telegram verkar:

```bash
cd ~/market-watch && .venv/bin/python -m src.main --test-notify
```

Får du meldinga i Telegram, er kanalen på plass. Set så `NOTIFIER=stdout` medan
du testar sjølve analysen, og køyr:

```bash
cd ~/market-watch && .venv/bin/python -m src.main --dry-run
```

Med `stdout` og `--dry-run` blir ingenting sendt — alt blir skrive i terminalen,
så du ser kva du *ville* fått. Køyr dette i nokre dagar og juster
`confidence_threshold` i `config.yaml` til støynivået passar deg.

For å teste før-opning-modusen spesifikt:

```bash
cd ~/market-watch && .venv/bin/python -m src.main --mode preopen --dry-run
```

---

---

## Korleis du veit at det framleis lever

Dette er verdt å tenkje på: **stille er den normale utgangen** frå verktøyet.
Så eit verktøy som er knekt ser nøyaktig ut som ein roleg marknad. Du kunne
gått tre veker og trudd at ingenting skjedde, medan API-nøkkelen var utgått.

Difor er det to meldingar som *ikkje* handlar om marknaden:

- **Feilmelding.** Klarar ikkje verktøyet å køyre 5 gonger på rad (~100 minutt),
  får du éi melding om det. Berre éi — eit knekt verktøy skal ikkje mase kvart
  20. minutt. Du får ei ny melding når det er oppe att.
- **Livsteikn.** Fredag kl. 17: *«market-watch lever. Siste veka: 812 køyringar,
  190 000 saker lesne, 3 varsel sendt.»* Då veit du at stille tyder stille.

Begge kan skruast av i `config.yaml` (`failure_alert_after`, `heartbeat_enabled`).

---

## Å skru på støynivået

Alt står i `config.yaml`:

| Innstilling | Effekt |
|---|---|
| `confidence_threshold` | Høgare = færre, sikrare meldingar. Start på `0.75`. Får du for mange, sett `0.85`. |
| `cooldown_minutes` | Minste tid mellom to varsel om same sak. |
| `max_alerts_per_day` | Hard sperre. Rekninga kan ikkje eksplodere. |
| `max_items_to_llm` | Kostnadstak per køyring. Færre = billegare. |
| `keywords` | Legg til selskap eller tema du vil følgje. |
| `feeds` | Legg til eller fjern nyheitskjelder. Kva RSS-feed som helst fungerer. |
| `max_news_age_hours` | Kor gamle saker som framleis blir vurderte. |

---

## Kva dette kostar

| Post | Per månad |
|---|---|
| Køyring på Macen din | 0 kr |
| Datakjelder | 0 kr (alt er opne feeds, ingen nøklar) |
| Telegram | 0 kr |
| Claude Haiku | ~15–30 kr |
| **Sum** | **~15–30 kr** |

Claude-kallet er heile kostnaden: ca. **0,03 kr per køyring**, og berre når
regelfilteret faktisk fann noko nytt. Vil du ned, senk `max_items_to_llm`.

Byter du til SMS seinare kjem ~15 kr/mnd for Twilio-nummeret pluss
~0,70 kr per melding oppå.

---

## Viss Macen er av (valfritt)

launchd køyrer berre når maskina er på og vaken. Er ho av eller i dvale, hoppar
køyringar over — det spelar sjeldan noka rolle, for verktøyet ser same nyheita
neste gong. Men skal det gå heilt uavhengig av deg, kan det køyre på GitHub
Actions i staden. Det krev GitHub-konto, repo og at du legg inn dei same tre
nøklane der.

<details>
<summary>Slik gjer du det</summary>

```bash
cd ~/market-watch && ./setup-github.sh <ditt-github-brukarnamn> market-watch
```

Lag eit **tomt** repo på github.com/new først. Skriptet sjekkar at ingen nøklar
er på veg med, commitar og pushar. Legg deretter inn under
**Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Verdi |
|---|---|
| `ANTHROPIC_API_KEY` | frå console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | frå @BotFather |
| `TELEGRAM_CHAT_ID` | frå `getUpdates` |

**Ei åtvaring om kvoten:** kvart 20. minutt blir ca. **836 køyringar i månaden**,
≈ 1670 av dei 2000 gratisminutta eit **privat** repo har. Marginen er tynn, og
går du tom stoppar verktøyet stille midt i månaden. Anten gjer du repoet
offentleg (ubegrensa minutt — nøklane ligg i Secrets, ikkje i koden), eller du
endrar cron til `*/30` i `.github/workflows/watch.yml`.

Køyrer du begge stader samtidig, får du dobbelt opp med meldingar. Skru av
Mac-varianten med `launchctl bootout gui/$(id -u)/no.sondre.market-watch`.

</details>

---

## Det du ikkje får

**Twitter/X er ikkje med.** X har ikkje lenger noko gratis eller billeg API-nivå
— det startar på rundt 200 USD i månaden, altså meir enn det tidoble av heile
budsjettet ditt. Reddit og nyheitsfeeds fangar mykje av det same, men eg vil
heller seie dette rett ut enn å late som om «alle plattformer» er dekt.

**Dette er ikkje investeringsråd.** Verktøyet samanfattar offentleg tilgjengeleg
informasjon. Det veit ikkje kva marknaden kjem til å gjere, og ingen gjer det.
Bruk det som eit varsel om at noko har skjedd — ikkje som ein instruks om å handle.
