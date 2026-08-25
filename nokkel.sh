#!/usr/bin/env bash
#
# Opnar eit vindauge der du kan skrive eller lime inn ein nøkkel.
# Nøkkelen går rett i .env. Han blir aldri vist i terminalen.
#
# Bruk:  ./nokkel.sh

set -uo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT"

[ -f ".env" ] || cp .env.example .env

status_linjer() {
  awk -F= '
    /^(ANTHROPIC_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=/ {
      v = substr($0, index($0, "=") + 1)
      printf "    %-20s %s\n", $1, (v == "" ? "manglar" : "OK")
    }
  ' .env
}

antal_manglar() {
  awk -F= '
    /^(ANTHROPIC_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=/ {
      v = substr($0, index($0, "=") + 1)
      if (v == "") n++
    }
    END { print n + 0 }
  ' .env
}

while true; do

  MANGLAR="$(antal_manglar)"
  if [ "$MANGLAR" -eq 0 ]; then
    echo ""
    echo "  Alle tre nøklane er på plass:"
    status_linjer
    echo ""
    echo "  Køyr no:  ./oppsett.sh"
    echo ""
    exit 0
  fi

  # Kva manglar? Vi spør om ein om gongen, i rekkjefølgje.
  NESTE="$(awk -F= '
    /^(ANTHROPIC_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=/ {
      v = substr($0, index($0, "=") + 1)
      if (v == "" && !funne) { print $1; funne = 1 }
    }
  ' .env)"

  case "$NESTE" in
    ANTHROPIC_API_KEY)
      LEDETEKST="Anthropic-nøkkelen — den lange som startar med sk-ant-"
      ;;
    TELEGRAM_BOT_TOKEN)
      LEDETEKST="Telegram-tokenet frå BotFather — tal, kolon, så bokstavar"
      ;;
    TELEGRAM_CHAT_ID)
      LEDETEKST="Telegram chat-ID — berre eit tal"
      ;;
    *)
      echo "  Fann ikkje ut kva som manglar. Sjekk .env."
      exit 1
      ;;
  esac

  # Dialogen kjem opp på skjermen. Svaret blir fanga i ein variabel og
  # blir aldri skrive ut - verken her eller i loggen.
  SVAR="$(osascript <<APPLESCRIPT 2>/dev/null
    set svar to display dialog "$LEDETEKST

Skriv han av frå telefonen, eller lim inn med Cmd+V." ¬
      default answer "" ¬
      with title "market-watch — $NESTE" ¬
      buttons {"Hopp over", "Lagre"} ¬
      default button "Lagre"
    if button returned of svar is "Hopp over" then
      return "__HOPP__"
    end if
    return text returned of svar
APPLESCRIPT
)"

  if [ -z "$SVAR" ]; then
    echo ""
    echo "  Avbrote. Ingenting er endra."
    echo ""
    echo "  Status:"
    status_linjer
    echo ""
    exit 0
  fi

  if [ "$SVAR" = "__HOPP__" ]; then
    echo "  Hoppa over $NESTE."
    # Marker at vi hoppa over, elles spør vi om det same i evig tid.
    echo ""
    echo "  Status:"
    status_linjer
    echo ""
    exit 0
  fi

  # Valider og skriv. Python får verdien på stdin, ikkje som argument,
  # så han ikkje dukkar opp i prosesslista.
  printf '%s' "$SVAR" | FELT="$NESTE" python3 -c '
import os, re, sys

felt = os.environ["FELT"]
verdi = sys.stdin.read().strip()

MONSTER = {
    "ANTHROPIC_API_KEY": (r"^sk-ant-[A-Za-z0-9_\-]{20,}$",
                          "skal starte med sk-ant- og vere over 90 teikn"),
    "TELEGRAM_BOT_TOKEN": (r"^\d{8,12}:[A-Za-z0-9_\-]{30,}$",
                           "skal vere tal, kolon, og minst 30 teikn etter"),
    "TELEGRAM_CHAT_ID": (r"^-?\d{5,15}$",
                         "skal vere berre eit tal"),
}

monster, forklaring = MONSTER[felt]

if not re.match(monster, verdi):
    print("")
    print("  Det du skreiv ser ikkje rett ut.")
    print("  %s (%s)" % (felt, forklaring))
    print("  Du skreiv %d teikn." % len(verdi))
    print("")
    print("  Vanlegaste feil: mellomrom framfor eller bak, eller at")
    print("  ein bokstav er skriven av feil. Prov igjen.")
    print("")
    sys.exit(2)

with open(".env") as f:
    linjer = f.read().split("\n")

funne = False
for i, linje in enumerate(linjer):
    if linje.lstrip().startswith("#"):
        continue
    if linje.split("=")[0].strip() == felt:
        linjer[i] = "%s=%s" % (felt, verdi)
        funne = True
        break
if not funne:
    linjer.append("%s=%s" % (felt, verdi))

with open(".env", "w") as f:
    f.write("\n".join(linjer))

print("  Lagra %s  (%d teikn)" % (felt, len(verdi)))
'

  # Feil format: dialogen kjem opp att med same felt.
  if [ $? -eq 2 ]; then
    continue
  fi

done
