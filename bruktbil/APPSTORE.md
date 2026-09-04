# Går det an å få dette i App Store?

Ja. Ingen ting ved denne appen er av slaget Apple avviser — det er ei teneste
for ein handel i den verkelege verda, akkurat som Vipps, FINN og bank-appane.
Men vegen dit har to portar, og Apple er den enklaste av dei.

Tala og satsane under er slik dei stod då dette blei skrive. **Alt som gjeld
løyve og regelverk må stadfestast med Finanstilsynet og ein advokat før du
tek imot ei einaste krone frå ein kjøpar.** Dette er ei teknisk vurdering, ikkje
juridisk rådgjeving.

---

## Port 1: Apple

Den lette. Ei sjekkliste, ikkje eit løyve.

**Det kostar 99 dollar i året.** Apple Developer Program. Vil du stå som
selskap og ikkje som privatperson — og det vil du, med tanke på ansvaret for
pengane — treng du organisasjonsnummer og eit D-U-N-S-nummer. Det er gratis og
tek nokre dagar.

**Dei 30 prosentane gjeld ikkje deg.** Dette er den viktigaste enkeltopplysninga
for forretningsmodellen. Apple krev kjøp i appen (og kuttar 15–30 %) for
*digitalt* innhald. For varer og tenester som blir brukte utanfor appen — ein
bil, ei kontraktsteneste, eit oppgjer — skal du bruke *andre* betalingsmåtar,
og Apple tek ingen ting. Gebyret på 199 kr er ditt. Bilen òg, sjølvsagt.

**Det Apple faktisk kjem til å stoppe deg på:**

- *Ein tynn nettside-innpakning.* Legg du berre denne webappen i eit
  WebView-skal, blir han avvist. Appen må gjere noko ein nettside ikkje gjer:
  push-varsel når motparten signerer, kamera for å dokumentere bilen, Face ID,
  Apple Wallet-kvittering, offline-visning av kontrakten.
- *Sletting av konto.* Kan brukaren lage konto i appen, må han kunne slette
  ho i appen. Med ein motpart og eit oppgjer i biletet må du tenkje gjennom kva
  «slett» tyder for ein handel som pågår, og for rekneskapsplikta etterpå.
- *Personvern-etiketten.* Du samlar namn, fødselsnummer og betalingsdata.
  Det skal deklarerast presist, og stemme med det appen faktisk gjer.
- *Demo-tilgang til vurderinga.* Apple sine folk må kunne gå gjennom heile
  flyten utan norsk BankID og utan å kjøpe ein bil. Testkontoar og eit
  demo-modus — omtrent det `demo.py` gjer no — er ikkje pynt, det er eit krav.

**Rekn to til fire veker frå ferdig app til godkjenning**, med ein runde eller
to fram og tilbake.

---

## Port 2: Pengane

Den tunge. Her ligg heile risikoen i prosjektet, og han har ingen ting med
programmering å gjere.

I det du tek imot kjøparen sine 180 000 kr og held dei til eigarskiftet er
gjennomført, driv du med **betalingsformidling for framande midlar**. Det er
konsesjonspliktig verksemd i Noreg. Du har tre vegar:

1. **Bli agent for eit betalingsføretak.** Raskast. Du sel tenesta i ditt namn,
   pengane ligg hos nokon som har løyvet, og du blir registrert som agent.
   Månader, ikkje år.
2. **Klientkonto gjennom bank eller advokat.** Ei ordning der pengane står på
   ein konto som juridisk ikkje er dine. Krev ein bankpartnar som vil ha deg.
3. **Eige løyve som betalingsføretak.** Månader til år, kapitalkrav, eige
   regelverk for kvitvasking. Ikkje der du startar.

Uansett veg følgjer **kvitvaskingslova** med: kundekontroll på begge partar,
overvaking, rapporteringsplikt. Det er difor BankID ikkje berre er ein signatur
i denne appen — det er kundekontrollen din.

Sel du forsikring eller lån ved sida av, er *det* òg konsesjonspliktig kvar for
seg (forsikringsformidling og låneformidling, begge under Finanstilsynet).
Enklaste start: berre lenkje ut til partnarane, ikkje formidle sjølv, til du
veit at hovudproduktet ber seg.

---

## Dei tre avtalane du må ha

| Kva | Kven | Kva det kostar deg |
|---|---|---|
| Kjøretøyopplysningar på skiltnummer | Statens vegvesen | avtale + pris per oppslag |
| Salsmelding og omregistrering | Statens vegvesen | avtale — og du må sjekke om dei i det heile opnar dette for tredjepart |
| BankID-innlogging og signering | Vipps, Signicat eller Criipto | fastpris + pris per signatur |

Den midtarste er den kritiske, og den einaste du bør undersøkje **før** du
skriv meir kode. Får du ikkje melde eigarskifte frå appen, må flyten lenkje
brukaren ut til Vegvesenet si eiga side og vente på stadfesting derifrå. Det
er framleis eit produkt — men det er eit anna produkt, og det bør du vite no.

Annonsedata frå FINN er **ikkje** noko du hentar utan avtale. Til det finst,
skriv brukaren inn skiltnummeret. Det tek fire sekund.

---

## Vegen eg ville gått

**No: nettapp, ingen App Store.** Det som ligg i denne mappa, med ekte
Vegvesen-oppslag og ekte BankID, og oppgjeret gjennom ein partnar. Ingen
app-vurdering, ingen 99 dollar, ingen ventetid. Du finn ut om folk vil bruke
det, og du finn det ut på nokre veker.

**Deretter: ekte app.** Når nokon faktisk har gjennomført ein handel og betalt
199 kr, byggjer du appen med push-varsel og kamera. Backend er alt skriven — det
er denne. React Native eller Flutter gir deg iOS og Android på éin gong;
SwiftUI gir betre kjensle, men dobbelt arbeid.

**Til slutt: der pengane er.** Gebyret på 199 kr er inngangen, ikkje målet.
Forsikring og lån betaler mykje meir per handel enn 199 kr gjer — men det er
tenester du berre får selje til folk som alt stoler på deg. Difor er trygt
oppgjer produktet, og alt det andre er det som kjem etterpå.

---

## Kort sagt

Apple er ikkje problemet, og dei tek ikkje 30 % av gebyret ditt. Pengane er
problemet. Kod ferdig flyten — han står her — men bruk den neste veka på to
telefonar: éin til Vegvesenet om salsmelding, og éin til eit betalingsføretak
om agentavtale. Svara derifrå avgjer kva app dette blir.
