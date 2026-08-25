#!/usr/bin/env bash
#
# Koplar dette repoet til GitHub og pushar.
#
# Bruk:
#   ./setup-github.sh <github-brukarnamn> <repo-namn>
#
# Døme:
#   ./setup-github.sh sondregrimen market-watch
#
# Du må ha laga repoet på github.com/new FØRST (tomt, utan README).

set -euo pipefail

cd "$(dirname "$0")"

USER_NAME="${1:-}"
REPO_NAME="${2:-market-watch}"

if [ -z "$USER_NAME" ]; then
  echo "Feil: du må oppgi GitHub-brukarnamnet ditt."
  echo "Bruk: ./setup-github.sh <github-brukarnamn> [repo-namn]"
  exit 1
fi

echo "==> Tryggleikssjekk: ligg det hemmelegheiter i repoet?"

LEAKED=0
for pattern in '.env' 'state.json'; do
  if git ls-files --error-unmatch "$pattern" >/dev/null 2>&1; then
    echo "    STOPP: $pattern er sport av git. Den skal ikkje til GitHub."
    LEAKED=1
  fi
done

# Leit etter noko som ser ut som ein ekte nøkkel i sporte filer.
if git grep -qIE 'sk-ant-[A-Za-z0-9]|[0-9]{9}:AA[A-Za-z0-9_-]{30}' -- . 2>/dev/null; then
  echo "    STOPP: fann noko som ser ut som ein API-nøkkel i sporte filer."
  LEAKED=1
fi

if [ "$LEAKED" -eq 1 ]; then
  echo ""
  echo "Avbryt. Fjern hemmelegheitene før du pushar."
  exit 1
fi
echo "    OK - ingen hemmelegheiter sporte."

echo ""
echo "==> Sjekkar at alt er commita"
if [ -n "$(git status --porcelain)" ]; then
  echo "    Du har ucommita endringar:"
  git status --short | sed 's/^/      /'
  echo ""
  read -r -p "    Commit dei no? [j/N] " svar
  if [ "$svar" = "j" ] || [ "$svar" = "J" ]; then
    git add -A
    git commit -q -m "Oppdateringar før push"
    echo "    Commita."
  else
    echo "    Avbryt."
    exit 1
  fi
else
  echo "    OK - alt er commita."
fi

REMOTE_URL="https://github.com/${USER_NAME}/${REPO_NAME}.git"

echo ""
echo "==> Koplar til ${REMOTE_URL}"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
  echo "    Oppdaterte eksisterande remote."
else
  git remote add origin "$REMOTE_URL"
  echo "    La til remote."
fi

echo ""
echo "==> Pushar til GitHub"
echo "    Blir du beden om brukarnamn og passord:"
echo "      Username: ${USER_NAME}"
echo "      Password: LIM INN DIN PERSONAL ACCESS TOKEN (ikkje GitHub-passordet)"
echo "    Token lagar du på: https://github.com/settings/tokens"
echo ""

git push -u origin main

echo ""
echo "=============================================================="
echo " Pusha. Nå må du leggje inn nøklane på GitHub:"
echo ""
echo " https://github.com/${USER_NAME}/${REPO_NAME}/settings/secrets/actions"
echo ""
echo "   New repository secret x3:"
echo "     ANTHROPIC_API_KEY    - frå console.anthropic.com"
echo "     TELEGRAM_BOT_TOKEN   - frå @BotFather"
echo "     TELEGRAM_CHAT_ID     - frå getUpdates"
echo ""
echo " Test så verktøyet manuelt her:"
echo " https://github.com/${USER_NAME}/${REPO_NAME}/actions"
echo "   -> market-watch -> Run workflow (dry_run står på true)"
echo "=============================================================="
