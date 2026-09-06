#!/usr/bin/env bash
# Gjer alt som kan gjerast automatisk. Koeyr denne foerst:
#
#     bash oppsett.sh
#
# Han lagar .env, hentar Apple-sertifikatet, installerer pakkar og
# seier til slutt kva som staar att - som er berre dei tinga eit
# menneske MAA gjere sjolv.

set -u
cd "$(dirname "$0")"

groen()  { printf '\033[32m%s\033[0m\n' "$1"; }
gul()    { printf '\033[33m%s\033[0m\n' "$1"; }
raud()   { printf '\033[31m%s\033[0m\n' "$1"; }
tittel() { printf '\n\033[1m%s\033[0m\n%s\n' "$1" "──────────────────────────────────────────────"; }

MANGLAR=()

tittel "1. Python-pakkar"
if python3 -m pip install -q -r requirements.txt 2>/dev/null; then
    groen "  Installerte"
else
    gul "  Klarte ikkje installere. Prøv: python3 -m pip install -r requirements.txt"
fi

tittel "2. ffmpeg (trengst for vassmerke paa delte videoar)"
if command -v ffmpeg >/dev/null 2>&1; then
    groen "  Finst: $(ffmpeg -version 2>&1 | head -1 | cut -c1-40)"
else
    gul "  Manglar. Deling blir av til han er installert."
    echo "     macOS:  brew install ffmpeg"
    echo "     Ubuntu: sudo apt install ffmpeg"
fi

tittel "3. Apple sitt rotsertifikat"
if [ -s config/AppleRootCA-G3.cer ]; then
    groen "  Finst allereie"
else
    for url in \
        "https://www.apple.com/certificateauthority/AppleRootCA-G3.cer" \
        "https://www.apple.com/appleca/AppleIncRootCertificate.cer"
    do
        if curl -sSf -o config/AppleRootCA-G3.cer "$url" 2>/dev/null; then
            groen "  Lasta ned frå $url"
            break
        fi
    done
    if [ -s config/AppleRootCA-G3.cer ]; then
        :
    else
        rm -f config/AppleRootCA-G3.cer
        raud "  Klarte ikkje laste ned."
        MANGLAR+=("Last ned 'Apple Root CA - G3' frå https://www.apple.com/certificateauthority/ og legg fila som videoapp/config/AppleRootCA-G3.cer")
    fi
fi

tittel "4. .env"
if [ -f .env ]; then
    groen "  Finst allereie (rører han ikkje)"
else
    cp .env.example .env
    NOKKEL=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    # Skriv inn den genererte tokennokkelen. Denne treng du aldri sjaa.
    python3 - "$NOKKEL" <<'PY'
import sys, pathlib
n = sys.argv[1]
p = pathlib.Path(".env")
p.write_text(p.read_text(encoding="utf-8").replace(
    "VIDEOAPP_TOKEN_NOKKEL=", f"VIDEOAPP_TOKEN_NOKKEL={n}"), encoding="utf-8")
PY
    groen "  Laga .env med ferdig generert tokennøkkel"
fi

# Kva som framleis manglar av noeklar
MM=$(grep -E '^MINIMAX_API_NOKKEL=.+' .env 2>/dev/null || true)
AN=$(grep -E '^ANTHROPIC_API_KEY=.+' .env 2>/dev/null || true)
[ -z "$MM" ] && MANGLAR+=("Lim MiniMax-nøkkelen din inn i .env på linja MINIMAX_API_NOKKEL=")
[ -z "$AN" ] && MANGLAR+=("Lim Anthropic-nøkkelen din inn i .env på linja ANTHROPIC_API_KEY=")

tittel "5. Testane"
if python3 -m pytest tests/ -q 2>&1 | tail -1 | grep -q passed; then
    groen "  Alle passerer"
else
    raud "  Noko feilar - køyr: python3 -m pytest tests/ -q"
fi

tittel "Kva som står att"
if [ ${#MANGLAR[@]} -eq 0 ]; then
    groen "  Ingenting. Start med:  python3 kjor.py"
else
    for m in "${MANGLAR[@]}"; do echo "  • $m"; done
    echo
    echo "  Når det er gjort:  python3 kjor.py"
fi
echo
