#!/usr/bin/env bash
# Launcher skua-lite untuk Linux/macOS.
#
# Menyiapkan virtualenv di dalam folder project, memastikan dependency
# terpasang, lalu menjalankan `python -m skua_lite` dengan argumen yang sama
# seperti saat kamu memanggil script ini.
#
#   ./JALANKAN_SKUA_LITE.sh                  -> prompt pilih mode
#   ./JALANKAN_SKUA_LITE.sh --mode farming   -> langsung mode farming
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Pilih interpreter Python 3 -------------------------------------------
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi
if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] Python 3 tidak ditemukan. Install dulu, mis.:" >&2
    echo "        Debian/Ubuntu : sudo apt install python3 python3-venv" >&2
    echo "        Fedora        : sudo dnf install python3" >&2
    echo "        macOS         : brew install python@3.12" >&2
    exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    echo "[ERROR] skua-lite butuh Python >= 3.11, versi terdeteksi:" >&2
    "$PYTHON_BIN" --version >&2
    exit 1
fi

# --- Siapkan virtualenv project (sekali saja) -----------------------------
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "[SETUP] Membuat virtualenv di $VENV_DIR ..."
    if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
        echo "[ERROR] Gagal membuat virtualenv di Debian/Ubuntu, jalankan dulu:" >&2
        echo "        sudo apt install python3-venv" >&2
        exit 1
    fi
fi

VENV_PY="$VENV_DIR/bin/python"

# --- Pastikan dependency terpasang ----------------------------------------
if ! "$VENV_PY" -c 'import cryptography' >/dev/null 2>&1; then
    echo "[SETUP] Memasang dependency project (cryptography) ..."
    "$VENV_PY" -m pip install --disable-pip-version-check --quiet --upgrade pip
    if ! "$VENV_PY" -m pip install --disable-pip-version-check --quiet -e "$SCRIPT_DIR"; then
        echo "[ERROR] Gagal memasang dependency. Periksa koneksi internet, lalu jalankan ulang." >&2
        exit 1
    fi
fi

# --- Jalankan bot ---------------------------------------------------------
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV_PY" -m skua_lite "$@"
