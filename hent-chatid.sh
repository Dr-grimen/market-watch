#!/usr/bin/env bash
#
# Finn TELEGRAM_CHAT_ID ut frå tokenet som allereie ligg i .env.
#
# Bruk:  ./hent-chatid.sh
#
# Krev at du har sendt minst éi melding til ditt eige bot først.

set -uo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT"

if [ ! -f ".env" ]; then
  echo "  Fann ingen .env. Køyr ./oppsett.sh først."
  exit 1
fi

# Same lesemåte som i oppsett.sh: siste verdi som ikkje er tom.
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

TOKEN="$(get_val TELEGRAM_BOT_TOKEN)"

if [ -z "$TOKEN" ]; then
  cat <<'NOTOKEN'

  Det ligg ingen TELEGRAM_BOT_TOKEN i .env enno.

  Hent han slik:
    1. Opne Telegram, søk opp  BotFather
    2. Trykk START, skriv  /newbot
    3. Vel eit namn, og eit brukarnamn som sluttar på 'bot'
    4. Du får ei linje som  8123456789:AAF2h-...
    5. Lim den inn i .env bak  TELEGRAM_BOT_TOKEN=

  Så køyrer du dette skriptet på nytt.

NOTOKEN
  exit 1
fi

echo ""
echo "  Spør Telegram etter meldingar til botet ditt ..."

SVAR="$(curl -s --max-time 15 "https://api.telegram.org/bot${TOKEN}/getUpdates")"

if [ -z "$SVAR" ]; then
  echo "  Fekk ikkje kontakt med Telegram. Sjekk nettet og prøv igjen."
  exit 1
fi

# Er tokenet feil, seier Telegram det rett ut.
if printf '%s' "$SVAR" | grep -q '"ok":false'; then
  echo ""
  echo "  Telegram avviste tokenet. Sjekk at du kopierte HEILE linja"
  echo "  frå BotFather, med kolonet i midten."
  echo ""
  exit 1
fi

# Plukk ut chat-id-ane. Bruker python fordi jq ikkje er standard på Mac.
IDS="$(printf '%s' "$SVAR" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
seen = []
for upd in data.get("result", []):
    for key in ("message", "edited_message", "channel_post"):
        chat = upd.get(key, {}).get("chat")
        if chat and chat.get("id") not in seen:
            seen.append(chat.get("id"))
for i in seen:
    print(i)
')"

if [ -z "$IDS" ]; then
  cat <<'TOMT'

  Tokenet verkar, men botet har ikkje fått nokon meldingar enno.

  Gjer dette:
    1. Søk opp DITT eige bot i Telegram (brukarnamnet du valde)
    2. Trykk START
    3. Send han ordet  hei

  Køyr så dette skriptet på nytt.

  (Telegram slettar gamle meldingar etter eit døgn. Er det lenge sidan
   du sende 'hei', send ein ny.)

TOMT
  exit 1
fi

ANTAL="$(printf '%s\n' "$IDS" | grep -c .)"

echo ""
if [ "$ANTAL" -eq 1 ]; then
  echo "  Din TELEGRAM_CHAT_ID er:  $IDS"
  echo ""
  echo "  Lim den inn i .env bak  TELEGRAM_CHAT_ID="
  echo "    open -e $PROJECT/.env"
else
  echo "  Fann fleire chattar. Din eigen er den botet fekk 'hei' frå:"
  printf '%s\n' "$IDS" | sed 's/^/    /'
  echo ""
  echo "  Er du i tvil: eit positivt tal er ein privatperson,"
  echo "  eit negativt tal er ei gruppe."
fi
echo ""
echo "  Køyr så:  ./oppsett.sh"
echo ""
