#!/usr/bin/env bash
#
# Tek det du har kopiert (Cmd+C) og legg det på rett linje i .env.
#
# Bruk:
#   1. Kopier ein nøkkel med Cmd+C
#   2. ./lim-inn.sh
#
# Skriptet kjenner sjølv att kva slags nøkkel det er, og skriv han
# aldri ut på skjermen.

set -uo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT"

if [ ! -f ".env" ]; then
  cp .env.example .env
fi

pbpaste | python3 -c '
import re, sys

verdi = sys.stdin.read().strip()

if not verdi:
    print("")
    print("  Utklippstavla er tom.")
    print("")
    print("  Merk nokkelen og trykk Cmd+C forst, sa koyr dette pa nytt.")
    print("")
    sys.exit(1)

# Kva slags nokkel er dette? Vi kjenner dei att pa forma.
if verdi.startswith("sk-ant-"):
    felt, namn = "ANTHROPIC_API_KEY", "Anthropic-nokkelen"
elif re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,}$", verdi):
    felt, namn = "TELEGRAM_BOT_TOKEN", "Telegram-tokenet"
elif re.match(r"^-?\d{5,15}$", verdi):
    felt, namn = "TELEGRAM_CHAT_ID", "Telegram chat-ID-en"
else:
    print("")
    print("  Eg kjende ikkje att det du har kopiert.")
    print("")
    print("  Det du kopierte er %d teikn langt og startar med: %s"
          % (len(verdi), verdi[:7] + "..."))
    print("")
    print("  Eg ventar meg ein av desse tre:")
    print("    sk-ant-...          Anthropic-nokkelen")
    print("    8123456789:AAF...   Telegram-tokenet")
    print("    123456789           Telegram chat-ID")
    print("")
    print("  Kopierte du for mykje? Ta med berre sjolve nokkelen,")
    print("  utan mellomrom eller linjeskift rundt.")
    print("")
    sys.exit(1)

if "\n" in verdi or " " in verdi:
    print("")
    print("  Det du kopierte har mellomrom eller linjeskift i seg.")
    print("  Merk berre sjolve nokkelen og prov igjen.")
    print("")
    sys.exit(1)

with open(".env") as f:
    linjer = f.read().split("\n")

# Byt ut den forste linja som definerer feltet. Finst det ikkje,
# legg vi det til nedst.
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

print("")
print("  Lagra %s i .env  (%d teikn)" % (namn, len(verdi)))
print("")
'

STATUS=$?
[ $STATUS -ne 0 ] && exit $STATUS

# Vis kva som står att, utan å avsløre verdiar.
echo "  Status no:"
awk -F= '
  /^(ANTHROPIC_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=/ {
    v = substr($0, index($0, "=") + 1)
    printf "    %-20s %s\n", $1, (v == "" ? "manglar" : "OK")
  }
' .env

MANGLAR="$(awk -F= '
  /^(ANTHROPIC_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=/ {
    v = substr($0, index($0, "=") + 1)
    if (v == "") n++
  }
  END { print n + 0 }
' .env)"

echo ""
if [ "$MANGLAR" -eq 0 ]; then
  echo "  Alle tre er på plass. Køyr no:"
  echo "    cd $PROJECT && ./oppsett.sh"
else
  echo "  Kopier neste nøkkel med Cmd+C, og køyr dette på nytt."
fi
echo ""
