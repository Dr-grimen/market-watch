#!/usr/bin/env bash
#
# Set opp market-watch til å køyre automatisk på denne Macen.
#
# Bruk:  ./oppsett.sh
#
# Skriptet gjer alt som kan gjerast automatisk. Manglar det ein nøkkel,
# stoppar det og seier nøyaktig kva du skal gjere.

set -uo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT"

PLIST_NAME="no.sondre.market-watch"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo ""
echo "  market-watch - oppsett"
echo "  ======================"
echo ""

# --- 1. Virtuelt miljø ------------------------------------------------

if [ ! -x ".venv/bin/python" ]; then
  echo "  [1/4] Lagar Python-miljø ..."
  python3 -m venv .venv || { echo "  Klarte ikkje lage miljøet."; exit 1; }
  .venv/bin/pip install -q --upgrade pip >/dev/null 2>&1
  .venv/bin/pip install -q -r requirements.txt || {
    echo "  Klarte ikkje installere avhengigheiter."; exit 1; }
  echo "        OK"
else
  echo "  [1/4] Python-miljø finst allereie. OK"
fi

# --- 2. .env ----------------------------------------------------------

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  [2/4] Laga .env frå malen."
else
  echo "  [2/4] .env finst allereie."
fi

# Les nøklane utan å skrive dei ut.
#
# Vi tek den SISTE verdien som ikkje er tom, ikkje den første. .env
# startar som ein kopi av malen der nøklane står tomme, og limer du
# dei inn nedst i fila i staden for å redigere den tomme linja, ville
# ein 'første treff'-variant lese den tomme og påstå at du mangla dei.
get_val() {
  awk -F= -v key="$1" '
    /^[[:space:]]*#/ { next }
    {
      k = $1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
      if (k != key) next
      v = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      gsub(/^["\047]|["\047]$/, "", v)
      if (v != "") last = v
    }
    END { print last }
  ' .env 2>/dev/null
}

BOT_TOKEN="$(get_val TELEGRAM_BOT_TOKEN)"
CHAT_ID="$(get_val TELEGRAM_CHAT_ID)"
API_KEY="$(get_val ANTHROPIC_API_KEY)"

MISSING=""
[ -z "$BOT_TOKEN" ] && MISSING="$MISSING TELEGRAM_BOT_TOKEN"
[ -z "$CHAT_ID" ]   && MISSING="$MISSING TELEGRAM_CHAT_ID"
[ -z "$API_KEY" ]   && MISSING="$MISSING ANTHROPIC_API_KEY"

if [ -n "$MISSING" ]; then
  cat <<GUIDE

  ---------------------------------------------------------------
  STOPP: det manglar nøklar i .env
  ---------------------------------------------------------------
  Manglar:$MISSING

  Eg kan ikkje hente desse for deg - dei krev di innlogging.
  Her er nøyaktig kva du gjer. Det tek ca. 6 minutt.

  === A. TELEGRAM (gratis) ===

   1. Opne Telegram på telefonen.
   2. Søk øvst etter:  BotFather
      Vel den med blå hake.
   3. Trykk START, skriv så:  /newbot
   4. Han spør om eit NAMN. Skriv t.d.:  Marknadsvarsel
   5. Han spør om eit BRUKARNAMN. Det må slutte på 'bot'
      og vere ledig. Prøv t.d.:  sondre_marknad_bot
      Er det oppteke, prøv med tal bak.
   6. Du får svar med ei linje som ser slik ut:

         8123456789:AAF2h-xxxxxxxxxxxxxxxxxxxxxxxxxxxx

      DET er TELEGRAM_BOT_TOKEN. Kopier heile linja.

   7. Lim tokenet inn i .env med ein gong (sjå C nedanfor),
      bak  TELEGRAM_BOT_TOKEN=

   8. I same Telegram: søk opp botet DITT (brukarnamnet frå steg 5),
      trykk START og send han ordet:  hei
      (Dette må du gjere, elles får ikkje botet lov å sende til deg.)

   9. Køyr så dette, så finn eg chat-ID-en for deg:

         cd "$PROJECT" && ./hent-chatid.sh

      Den skriv ut talet du skal ha bak  TELEGRAM_CHAT_ID=

  === B. ANTHROPIC (Claude) ===

   1. Gå til:  https://console.anthropic.com
   2. Lag konto / logg inn.
   3. Billing -> legg inn kort og fyll på 5 USD.
      (Det held i mange månader. Verktøyet bruker ca. 15-30 kr/mnd.)
   4. Settings -> API Keys -> Create Key.
   5. Kopier nøkkelen. Han startar med  sk-ant-
      VIKTIG: du får sjå han berre éin gong.

  === C. LIM DEI INN ===

   Køyr denne kommandoen for å opne .env i eit tekstredigeringsprogram:

       open -e "$PROJECT/.env"

   Fyll ut slik (ingen mellomrom rundt = , ingen hermeteikn):

       ANTHROPIC_API_KEY=sk-ant-...
       TELEGRAM_BOT_TOKEN=8123456789:AAF2h-...
       TELEGRAM_CHAT_ID=123456789

   Lagre (Cmd+S), lukk, og køyr dette skriptet på nytt:

       cd "$PROJECT" && ./oppsett.sh

  ---------------------------------------------------------------

GUIDE
  exit 1
fi

echo "  [3/4] Alle nøklar er på plass. Testar Telegram ..."

if .venv/bin/python -m src.main --test-notify >/tmp/mw-test.log 2>&1; then
  echo "        OK - sjekk telefonen, du skal ha fått ei melding."
else
  echo ""
  echo "        Telegram svarte ikkje som venta. Detaljar:"
  grep -E "^\[notify\]|error|Error" /tmp/mw-test.log | head -5 | sed 's/^/          /'
  echo ""
  echo "        Vanlegaste årsak: du har ikkje sendt ei melding til"
  echo "        botet ditt enno. Gjer det, og køyr skriptet på nytt."
  exit 1
fi

# --- 4. Automatisk køyring -------------------------------------------

echo "  [4/4] Set opp automatisk køyring kvart 20. minutt ..."

mkdir -p logs
mkdir -p "$HOME/Library/LaunchAgents"

sed "s|__PROJECT__|$PROJECT|g" "${PLIST_NAME}.plist" > "$PLIST_DEST"

# Fjern ei eventuell gammal utgåve før vi lastar den nye.
launchctl bootout "gui/$(id -u)/${PLIST_NAME}" >/dev/null 2>&1
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null \
  || launchctl load "$PLIST_DEST" 2>/dev/null

if launchctl list | grep -q "$PLIST_NAME"; then
  echo "        OK - verktøyet køyrer nå automatisk."
else
  echo "        Klarte ikkje starte automatisk køyring."
  echo "        Prøv manuelt:  launchctl load $PLIST_DEST"
  exit 1
fi

cat <<DONE

  ==============================================================
   Ferdig. Verktøyet køyrer nå av seg sjølv kvart 20. minutt,
   så lenge Macen er på.

   Du får melding på Telegram BERRE når noko er sikkert nok.
   Er det uklart, høyrer du ingenting. Det er meininga.

   Sjekke at det lever:
     tail -f "$PROJECT/logs/market-watch.log"

   Skru det av att:
     launchctl bootout gui/\$(id -u)/${PLIST_NAME}

   Kvar fredag kl. 17 får du eit livsteikn, så du veit at
   stille faktisk tyder stille.
  ==============================================================

DONE
