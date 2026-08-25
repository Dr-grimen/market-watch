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

Køyrer **kvart 20. minutt** gjennom heile den amerikanske handelsdagen, og kvar
time om morgonen. Mellom 14:00 og 15:30 norsk tid skiftar verktøyet automatisk
til *før-opning-modus* og spør spesifikt: **tyder noko på at børsen opnar opp?**

To detaljar som gjer at det faktisk fungerer:

- **Kryss-kjelde-teljing.** Melder fem aviser same sak, tel det som eit styrkesignal.
  Ei einsleg overskrift veg lite.
- **Nær-duplikat-samanslåing.** «Fed's Collins says rates may rise» og «Collins:
  holding rates hangs on inflation» er same hending. Utan dette ville tre av
  tolv Claude-plassar gått til å lese den same nyheita om att.

---

## Det du må gjere sjølv

Eg kan ikkje opprette kontoar eller handtere betalingskort for deg. Desse stega
må du ta sjølv:

- [ ] **GitHub-konto** — https://github.com (gratis). Trengst for at verktøyet skal køyre døgnet rundt.
- [ ] **Anthropic API-nøkkel** — https://console.anthropic.com → Settings → API Keys.
      Du må leggje inn eit kredittkort og fylle på litt saldo (5 USD held lenge).
- [ ] **Telegram-bot** (gratis):
      1. Opne Telegram og søk opp **@BotFather**.
      2. Send `/newbot`, vel eit namn. Du får eit **token** — det er `TELEGRAM_BOT_TOKEN`.
      3. Søk opp din nye bot og send han ei melding (kva som helst, t.d. `hei`).
      4. Opne `https://api.telegram.org/bot<TOKEN>/getUpdates` i nettlesaren.
         Talet under `"chat":{"id": ...}` er `TELEGRAM_CHAT_ID`.

Telefonnummeret ditt trengst ikkje — Telegram sender til bot-samtalen, ikkje til
eit nummer. (Skulle du seinare byte tilbake til SMS, treng du i tillegg ein
Twilio-konto frå https://twilio.com/try-twilio.)

Ikkje lim nøklane inn i ei chat eller inn i koden. Dei skal berre to stader:
`.env` lokalt (som er i `.gitignore`) og GitHub Secrets.

---

## Test lokalt først

```bash
cd ~/market-watch && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Kopier `.env.example` til `.env` og lim inn nøklane dine. Sjekk så oppsettet:

```bash
cd ~/market-watch && .venv/bin/python -m src.main --doctor
```

Den seier rett ut kva som manglar, og testar samtidig at pris- og
nyheitskjeldene svarer. Når han er grøn, test at Telegram verkar:

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

## Sett det i skya

```bash
cd ~/market-watch && git init && git add -A && git commit -m "market-watch"
```

Lag eit **privat** repo på GitHub og push. Så, i repoet:

**Settings → Secrets and variables → Actions → New repository secret** — legg inn:

| Secret | Verdi |
|---|---|
| `ANTHROPIC_API_KEY` | frå console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | frå @BotFather |
| `TELEGRAM_CHAT_ID` | frå `getUpdates` |

Telegram er standard, så du treng ikkje setje noko under **Variables**. Vil du
seinare over på SMS, set `NOTIFIER` til `twilio_sms` der og legg inn dei fire
`TWILIO_*`/`ALERT_PHONE_NUMBER`-secrets.

Så: **Actions**-fana → `market-watch` → **Run workflow** for å teste manuelt
(`dry_run` står på `true` som standard).

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
| GitHub Actions | 0 kr — men sjå åtvaringa under |
| Datakjelder | 0 kr (alt er opne feeds, ingen nøklar) |
| Telegram | 0 kr |
| Claude Haiku | ~15–30 kr |
| **Sum** | **~15–30 kr** |

Claude-kallet er heile kostnaden: ca. **0,03 kr per køyring**, og berre når
regelfilteret faktisk fann noko nytt. Vil du ned, senk `max_items_to_llm`.

### Åtvaring om GitHub-kvoten

Kvart 20. minutt blir ca. **836 køyringar i månaden**, ≈ 1670 av dei
2000 gratisminutta eit **privat** repo har. Det går, men marginen er tynn —
og går du tom, stoppar verktøyet stille midt i månaden.

To utvegar:

- **Gjer repoet offentleg** → ubegrensa Actions-minutt. Trygt her: nøklane ligg
  i GitHub Secrets, ikkje i koden, og `.env` er i `.gitignore`. Det einaste
  utanforståande ser er kjeldelista di.
- **Eller behald det privat** og endre cron til `*/30` i
  `.github/workflows/watch.yml`. Då bruker du ~1100 minutt.

Byter du til SMS seinare kjem ~15 kr/mnd for Twilio-nummeret pluss
~0,70 kr per melding oppå.

---

## Det du ikkje får

**Twitter/X er ikkje med.** X har ikkje lenger noko gratis eller billeg API-nivå
— det startar på rundt 200 USD i månaden, altså meir enn det tidoble av heile
budsjettet ditt. Reddit og nyheitsfeeds fangar mykje av det same, men eg vil
heller seie dette rett ut enn å late som om «alle plattformer» er dekt.

**Dette er ikkje investeringsråd.** Verktøyet samanfattar offentleg tilgjengeleg
informasjon. Det veit ikkje kva marknaden kjem til å gjere, og ingen gjer det.
Bruk det som eit varsel om at noko har skjedd — ikkje som ein instruks om å handle.
