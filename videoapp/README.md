# videoapp — ryggrada

Bilde inn, prompt inn, video ut. Éin skjerm, to felt.

Dette er **ikkje** appen. Det er dei fire delane som er dyre å gjere feil,
bygde først: kredittrekneskapen, leverandørrutinga, promptforbetringa og
prismodellen. Skjermane er lette å byte; desse er det ikkje.

> Dette ligg mellombels i `market-watch`-repoet fordi utviklingsgreina
> peikar hit. Det bør flyttast til eit eige repo før det veks vidare.

---

## Kom i gang

```bash
pip install -r requirements.txt
python3 okonomi.py          # kva appen tener og brenn
python3 -m pytest tests/ -q # 58 testar
```

---

## Prisen: 149 kr = 250 kredittar

**25 genereringar på standard, som blir ~19 ferdige videoar** når folk
regenererer litt. Vel dei HD i staden, blir det 8.

Kvota er i **kredittar, ikkje videoar**. Det er ikkje kosmetikk: lovar du
«25 videoar», kan ein abonnent veksle dei inn i HD og bli ulønsam for deg.
Med kredittar kostar ein HD-video tre gonger så mykje av kvota, og
rekninga går opp uansett kva han vel. `test_pricing.py` held det slik.

**Regenerering kostar kredittar.** Det gjer kvota til eit hardt tak på
kva ein abonnent kan koste deg. Utan det kan ein kravstor brukar gå i
minus — testane fann akkurat det tilfellet. Bieffekt: masaren blir
faktisk meir lønsam enn snittbrukaren, fordi han brenn kvote på
genereringar men lagar færre ferdige videoar å lagre.

| bruk | forteneste per abonnent |
|---|---|
| Venta (60 % av kvota) | +84 kr |
| Heile kvota brukt | +55 kr |
| Heile kvota + masar 2,5x | +74 kr |

Det tåler ein kundeanskaffingskostnad på 55 kr i månaden — sjølv i
verste fall.

### Kvifor «75 kr til MiniMax» ikkje går opp

Reknestykket gløymer to ting: Apple tek 22 kr av dei 149 først, og kvar
*levert* video dreg med seg 2 kr i lagring, CDN og moderering på toppen
av genereringa. 75 kr i GPU-forbruk blir 37 videoar som til saman kostar
148 kr — og du sit att med minus 22.

Det rare resultatet: **den billegaste modellen tapar mest.** Billeg GPU
gir fleire videoar innanfor budsjettet, og kvar video dreg med seg dei
faste 2 kronene uansett.

---

## Ingenting er gratis

`gaver.ved_registrering` står på 0. Det fjernar den største enkeltrisikoen
— 1 million registreringar ville kosta 3,4 millionar kroner før eit
einaste sal.

Prisen for det er konvertering: folk lastar ned appar for å prøve dei.
Vil du snu på det seinare, er mellomtinget det farlege — nokre kredittar
som ikkje rekk til éin video er verre enn ingen, fordi brukaren sit att
med inntrykket av at appen berre vil ha pengar. Anten gi nok til éin
ordentleg video, eller ingenting. Testen `test_gratisgaava_er_null_eller_daekker_ein_video`
held den grensa.

---

## To ting bygginga avdekte

**GPU-en er ikkje lenger den største kostnaden.** Med 5-sekunds
bilde-til-video kostar sjølve genereringa ~1,71 kr, medan lagring, CDN,
transkoding og moderering er sett til 2,00 kr. Dei faste kostnadene er
altså *større* enn GPU-en. Det tyder at å jakte på ein 20 % billegare
leverandør flyttar lite — å få ned CDN- og lagringskostnaden flyttar meir.
Mål dei faste kostnadene tidleg og oppdater `faste_kroner_per_video`.

**HD-nivået har berre éin leverandør.** `okonomi.py` seier det rett ut.
Går MiniMax ned, kan HD ikkje leverast i det heile. Anten aktiver ein
leverandør til på 1080p, eller ver klar over at HD har ein enkeltfeilkjelde.

---

## Delane

### `config/providers.yaml` — den einaste fila du justerer

Kostnader, nivå, kredittprisar og Apple-kuttet. Ingen prisar er hardkoda
i Python. Kven som er billegast byttar med nokre månaders mellomrom, så
dette er ei driftsfil, ikkje ei kodeavgjerd. Gå gjennom han månadleg.

Oppløysing er **bøtter** (`lav`/`medium`/`hd`), ikkje tal. Kvar leverandør
seier kva bøtta heiter hos seg. Utan dette blir «720p» og «768p» to ulike
ting, og den billegaste leverandøren blir stille aldri vald.

### `app/ledger.py` — kredittrekneskapen

Dobbel bokføring. Tre reglar:

1. **Posteringane summerer til null.** Kredittar blir aldri skapte eller
   øydelagde, berre flytta. `ledger.stemmer()` er ein helsesjekk du bør
   køyre i produksjon.
2. **Idempotensnøkkel på alt.** Ringer appen to gonger fordi nettet datt,
   skjer det éin gong. Bruk Apple si kvitterings-id som nøkkel på kjøp.
3. **Reserver før generering, gjer opp etterpå.** Feilar leverandøren,
   får brukaren kredittane att. Trekk-først gir sinte brukarar og refusjonar.

Saldoen er alltid summen av posteringane. Det finst ikkje eit saldofelt
som kan kome ut av takt med historikken.

`rydd_gamle_reservasjonar()` må køyrast som cron. Utan han blir kredittar
ståande fast når ein jobb kræsjar.

### `app/providers/router.py` — billegast først, aldri ned

Vel billegaste aktive leverandør som klarer nivået, og fell over ved
mellombels feil. Brukaren skal aldri sjå ei feilmelding frå ein leverandør.

Skilnaden mellom `MellombelsFeil` og `VarigFeil` er viktig: timeout og
503 skal falle over, men eit bilde som blei avvist av moderering skal
**ikkje** sendast til fire leverandørar. Det brenn berre pengar.

Straumbrytaren stenger ute ein leverandør etter fem feil på rad, fordi
det å prøve nokon som er nede kostar tid på kvar einaste jobb.

### `app/prompt.py` — det som gjer éin knapp mogleg

Brukaren skriv «få han til å gå». Videomodellen treng kamerarørsle, lys
og tempo. Vi fyller inn resten med Claude Haiku.

**Feilar dette, stoppar vi ikkje videoen.** Brukaren har betalt kredittar.
At omskrivaren er nede er vårt problem — då sender vi teksten deira rå.

Modellen er `claude-haiku-4-5` fordi dette går på kvar einaste generering.
Vil du ha betre promptar, byt `MODELLAR` i fila — `claude-opus-5` er klart
flinkare, men kostar vesentleg meir per kall.

### `app/moderering.py` — portvakta

Apple slepp deg ikkje inn utan. Fire kategoriar: barn, verkelege
personar, seksuelt, ulovleg. Alt blir logga — utan sjølve biletet.

Ho **feilar lukka**. Promptforbetringa feilar open (ned → lag videoen
likevel); moderering feilar lukka (ned → lag ingenting). Asymmetrien er
med vilje: ein dårleg prompt gir ein kjedeleg video, eit bilde som slepp
gjennom kan koste deg appen.

Treff på «barn» er **meldepliktig** — det skal til politiet, ikkje berre
blokkerast. Avklar rutinen med advokat før lansering.

### `app/jobb.py` — heile vegen

Moderer → reserver → forbetre → generer → gjer opp eller frigi.
Rekkjefølgja avgjer om folk blir trekte for noko dei ikkje fekk.
Moderering *før* reservasjon: avviste brukarar har ikkje betalt noko.
Kvar veg ut av funksjonen gjer anten opp eller frigir — testane sjekkar
at ingen kredittar blir hengande.

### `okonomi.py` — før du endrar ein pris

Marginar per nivå, kva failover gjer med dei, gratisbrenn per
registreringsvolum, og abonnementsmatematikken.

```bash
python3 okonomi.py --forsok 2.5      # kravstore brukarar som regenererer
python3 okonomi.py --brukarar 100000
```

Tabellen «kva ein pris ber» svarar direkte på *kor mange videoar får dei
for X kroner*, med marginkravet frå konfigen lagt inn.

### `tests/test_pricing.py` — marginvakta

Desse testar ikkje kode, dei testar **forretninga**. Set nokon
kredittprisen for lågt, feilar bygget. Dei sjekkar mellom anna at
gratisgåva faktisk rekk til minst éin video — feilen i den opphavlege
planen var 20 gratiskredittar mot ein video til 50.

---

## Det som ikkje er bygd

- API-laget og kø (jobbane er synkrone i dag)
- Lagring og CDN for ferdige videoar
- Apple-kvitteringsvalidering mot `ledger.kjop()`
- Vassmerke og deling — vekstmotoren
- Malar, som er det som gjer novelty om til vane
- Sjølve appen

---

## Før lansering

**Personvern.** MiniMax og Seedance ligg utanfor EØS. Å sende
brukarbilde med ansikt dit er ei overføring av persondata etter GDPR
kapittel V og treng eit rettsleg grunnlag. Det må stå i vilkåra, og du
bør ha ein EØS-leverandør i ruteren for dei som krev det —
`wan_serverless` er sett av til det, men er ikkje testa.

**Rettar.** Kven eig videoen? Avklar det i vilkåra, og sjekk om
leverandøren sine vilkår i det heile tillet kommersiell bruk.

**Konkurransen.** Trekning med krav om kjøp er lotteri etter norsk
lotterilov og krev løyve frå Lotteritilsynet. Ein ferdigheitskonkurranse
der ein jury kårar beste video er det ikkje. Apple krev i tillegg at du
står som sponsor og at Apple blir fråskrivne ansvar.

**Skala.** Flaskehalsen er ikkje serverane dine — det er kvoten hos
leverandøren. 1 million brukarar med éin video dagleg er ~12 genereringar
i sekundet, altså ~700 samtidige jobbar. Ingen gir deg det utan ein stor
avtale. Difor er fleirleverandør-ruting bygd inn frå første dag, og
difor må produktet vere asynkront: brukaren ventar ikkje i appen, han
får push når videoen er klar.
