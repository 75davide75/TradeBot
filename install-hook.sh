#!/bin/bash
# Installa un hook che BLOCCA i commit contenenti segreti.
#
# Il .gitignore protegge da "git add ." ma non da "git add -f config.json"
# ne' da un file nuovo che nessuno ha pensato di ignorare. Questo hook
# controlla il contenuto di cio' che stai per committare, non il nome.
#
# Uso (dal Mac, nella cartella del progetto):  bash install-hook.sh

set -e
cd "$(dirname "$0")"
[ -d .git ] || { echo "Non e' un repo git. Fai prima 'git init'."; exit 1; }

mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/bin/bash
# Blocca il commit se trova segreti nei file in staging.
fail=0

if git diff --cached --name-only | grep -qx "config.json"; then
  echo "BLOCCATO: stai committando config.json (contiene il token del bot)."
  echo "          git restore --staged config.json"
  fail=1
fi

# Token Telegram: 8-10 cifre, due punti, 35 caratteri base64-like.
if git diff --cached -U0 | grep -qE '[0-9]{8,10}:[A-Za-z0-9_-]{35}'; then
  echo "BLOCCATO: c'e' quello che sembra un token Telegram nel diff."
  fail=1
fi

# Chiavi private di ogni tipo.
if git diff --cached -U0 | grep -qE 'BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY'; then
  echo "BLOCCATO: c'e' una chiave privata nel diff."
  fail=1
fi

if [ $fail -eq 1 ]; then
  echo
  echo "Se e' un falso positivo:  git commit --no-verify"
  echo "Ma leggi due volte prima: su un repo pubblico non si torna indietro."
  echo "Un segreto pubblicato resta nella storia di git anche se lo cancelli"
  echo "col commit dopo. L'unico rimedio vero e' rigenerare il token."
  exit 1
fi
HOOK

chmod +x .git/hooks/pre-commit
echo "Hook installato in .git/hooks/pre-commit"
echo
echo "Verifica che funzioni:"
echo "  git add -f config.json && git commit -m test"
echo "  (deve essere BLOCCATO, poi: git restore --staged config.json)"
