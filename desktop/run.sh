#!/usr/bin/env bash
# run.sh — Inicializador da aplicação desktop
#
# Uso:
#   ./run.sh              → modo normal (conecta ao ESP32)
#   ./run.sh --simulate   → modo simulação (sem hardware)
#   ./run.sh --host 192.168.1.50 --port 8080   → IP customizado
#
# Este script garante que o venv correto seja usado,
# evitando o erro de Pillow/ImageTk do Python do sistema.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

# ── 1. Cria o venv se ainda não existir ─────────────────────────────
if [ ! -f "$VENV_DIR/bin/python3" ]; then
    echo "[run.sh] Criando ambiente virtual em .venv/ ..."
    python3 -m venv "$VENV_DIR"
fi

# ── 2. Instala/atualiza dependências ────────────────────────────────
echo "[run.sh] Verificando dependências..."
"$VENV_DIR/bin/pip" install --quiet -r "$REQUIREMENTS"

# ── 3. Executa a aplicação ──────────────────────────────────────────
echo "[run.sh] Iniciando aplicação..."
"$VENV_DIR/bin/python3" "$SCRIPT_DIR/src/main.py" "$@"
