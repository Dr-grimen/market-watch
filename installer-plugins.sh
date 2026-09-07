#!/usr/bin/env bash
# Installerer Claude Code-plugins og -skills på DENNE maskina.
#
#   ./installer-plugins.sh            # dei du bad om
#   ./installer-plugins.sh --ekstra   # + fem som faktisk hjelper på dette prosjektet
#
# Køyr han på nytt så mykje du vil - alt som alt er installert, blir hoppa over.
# Skriptet stoppar ikkje om éin plugin feilar; det tel opp og seier frå til slutt.

set -u

EKSTRA=0
[[ "${1:-}" == "--ekstra" ]] && EKSTRA=1

if ! command -v claude >/dev/null 2>&1; then
  echo "Fann ikkje 'claude' på PATH. Installer Claude Code fyrst: https://claude.com/claude-code"
  exit 1
fi

feil=0
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
hopp() { printf '  \033[33m·\033[0m %s\n' "$*"; }
nei()  { printf '  \033[31m✘\033[0m %s\n' "$*"; feil=$((feil+1)); }

# ---------------------------------------------------------------- marknader
# Format: lokalt namn | github owner/repo
# Det lokale namnet er det som står i marketplace.json i kvart repo, og det er
# det som må brukast etter @ i "plugin@marknad".
MARKNADER=(
  "claude-plugins-official|anthropics/claude-plugins-official"
  "impeccable|pbakaus/impeccable"
  "thedotmack|thedotmack/claude-mem"
  "ui-ux-pro-max-skill|nextlevelbuilder/ui-ux-pro-max-skill"
  "taste|obakeng-develops/taste"
  "claude-video|bradautomates/claude-video"
)

echo "Marknader:"
kjende="$(claude plugin marketplace list 2>/dev/null || true)"
for m in "${MARKNADER[@]}"; do
  namn="${m%%|*}"; repo="${m##*|}"
  if grep -q "$namn" <<<"$kjende"; then
    hopp "$namn (finst frå før)"
  elif claude plugin marketplace add "$repo" >/dev/null 2>&1; then
    ok "$namn  ($repo)"
  else
    nei "$namn  ($repo)"
  fi
done

# ---------------------------------------------------------------- plugins
PLUGINS=(
  "claude-code-setup@claude-plugins-official"   # "Claude code setup" - Anthropic sin eigen
  "playwright@claude-plugins-official"          # "playwright cli" - Microsoft sin MCP-server
  "impeccable@impeccable"                       # frontend-design
  "claude-mem@thedotmack"                       # minne på tvers av økter
  "ui-ux-pro-max@ui-ux-pro-max-skill"           # UI/UX-database
  "taste@taste"                                 # /taste, /taste-audit, /taste-learn
  "watch@claude-video"                          # "Claude watch": video -> bilete + transkripsjon
)
if (( EKSTRA )); then
  PLUGINS+=(
    "pyright-lsp@claude-plugins-official"          # Python-typar og gå-til-definisjon
    "claude-md-management@claude-plugins-official" # repoet manglar CLAUDE.md; denne lagar og held han ved like
    "code-review@claude-plugins-official"          # fleire agentar som les PR-en din
    "context7@claude-plugins-official"             # ferske docs for anthropic, feedparser, requests
    "security-guidance@claude-plugins-official"    # varslar om nøklar i kode o.l.
  )
fi

echo "Plugins:"
installerte="$(claude plugin list 2>/dev/null || true)"
for p in "${PLUGINS[@]}"; do
  if grep -q "${p%%@*}" <<<"$installerte"; then
    hopp "$p (finst frå før)"
  elif claude plugin install "$p" >/dev/null 2>&1; then
    ok "$p"
  else
    nei "$p   (prøv manuelt: claude plugin install $p)"
  fi
done

# ---------------------------------------------------------------- skills utan marknad
# Desse blir ikkje distribuerte som plugins; forfattarane seier "klon inn i ~/.claude".
klon() {  # klon <repo-url> <målmappe>
  local url="$1" maal="$2"
  if [[ -d "$maal/.git" ]]; then
    git -C "$maal" pull -q --ff-only >/dev/null 2>&1 && hopp "$(basename "$maal") (oppdatert)" || nei "$(basename "$maal") (git pull feila)"
  elif git clone -q "$url" "$maal" >/dev/null 2>&1; then
    ok "$(basename "$maal")  <- $url"
  else
    nei "$(basename "$maal")  <- $url"
  fi
}

echo "Skills (git clone):"
mkdir -p ~/.claude/skills ~/.claude/commands
klon https://github.com/img2threejs/img2threejs.git          ~/.claude/skills/img2threejs
klon https://github.com/tenfoldmarc/website-builder-setup.git ~/.claude/commands/website-builder-setup   # UI/UX Pro Max + Framer Motion + 21st.dev

# task-observer ligg inne i eit større repo; vi hentar berre mappa med SKILL.md.
if [[ -d ~/.claude/skills/task-observer ]]; then
  hopp "task-observer (finst frå før)"
else
  tmp="$(mktemp -d)"
  if git clone -q --depth 1 https://github.com/rebelytics/one-skill-to-rule-them-all.git "$tmp" >/dev/null 2>&1; then
    kjelde="$(dirname "$(find "$tmp" -name SKILL.md -not -path '*/.git/*' | head -1)")"
    if [[ -n "$kjelde" ]] && cp -R "$kjelde" ~/.claude/skills/task-observer; then
      ok "task-observer  (hugs: legg aktiveringslinja frå references/environments.md i CLAUDE.md)"
    else
      nei "task-observer (fann ikkje SKILL.md i repoet)"
    fi
  else
    nei "task-observer (git clone feila)"
  fi
  rm -rf "$tmp"
fi

# ---------------------------------------------------------------- Perplexity (MCP, ikkje plugin)
echo "MCP:"
if claude mcp list 2>/dev/null | grep -q '^perplexity'; then
  hopp "perplexity (finst frå før)"
elif [[ -n "${PERPLEXITY_API_KEY:-}" ]]; then
  if claude mcp add perplexity -e "PERPLEXITY_API_KEY=$PERPLEXITY_API_KEY" -- npx -y @perplexity-ai/mcp-server >/dev/null 2>&1; then
    ok "perplexity"
  else
    nei "perplexity"
  fi
else
  hopp "perplexity - hoppa over. Hent nøkkel på https://www.perplexity.ai/settings/api og køyr:"
  echo "      PERPLEXITY_API_KEY=pplx-... ./installer-plugins.sh"
fi

# ---------------------------------------------------------------- dei som ikkje er plugins
cat <<'MELDING'

Ikkje installert - desse er ikkje Claude Code-plugins:
  · OmniRoute   - lokal API-gateway som ruter trafikken din via tredjepartar.
                  https://github.com/diegosouzapw/OmniRoute  (les kva den ser før du bruker han på jobb)
  · Headroom    - macOS-menylinjeapp med lokal proxy for tokenkomprimering.
                  https://extraheadroom.com
  · awesome-claude-design - ei samling DESIGN.md-filer du legg i rota av eit
                  frontend-prosjekt. Dette repoet har ingen frontend.
                  https://github.com/VoltAgent/awesome-claude-design
MELDING

echo
if (( feil == 0 )); then
  echo "Ferdig. Start Claude Code på nytt (eller køyr /reload-plugins) så er alt aktivt."
else
  echo "Ferdig, men $feil ting feila (sjå ✘ over). Køyr skriptet på nytt, eller kommandoen som står bak."
  exit 1
fi
