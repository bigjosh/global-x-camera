#!/bin/bash
# Local macOS launcher; downloads only pyserial into this folder's virtualenv.
set -u
cd -- "$(dirname -- "$0")" || exit 1

finish() {
    result=$?
    if [ "$result" -ne 0 ]; then
        printf '\nInstallation stopped. Keep any camera programming state unchanged.\n'
    fi
    printf '\nPress Return to close this window.\n'
    read -r answer || true
}
trap finish EXIT

printf 'Global X Camera firmware installer\n\n'
PYTHON=""
while [ -z "$PYTHON" ]; do
    for candidate in \
        /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
        /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        if [ -x "$candidate" ] && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
            PYTHON="$candidate"
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        printf 'Python 3.10 or newer is needed to run this installer.\n'
        printf 'Install the macOS Python package from https://www.python.org/downloads/macos/\n'
        printf 'Use its normal installer; no coding setup or project files are needed.\n'
        printf 'Press Return after installing Python, or type q to stop: '
        read -r answer || exit 1
        if [ "$answer" = q ]; then exit 1; fi
    fi
done

if [ ! -x .venv/bin/python ]; then
    printf 'Preparing a private Python environment in this installer folder...\n'
    "$PYTHON" -m venv .venv || exit 1
fi
if ! .venv/bin/python -c 'import serial; assert serial.VERSION == "3.5"' >/dev/null 2>&1; then
    printf 'Installing the serial-port library (pyserial 3.5) into that environment...\n'
    .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt || exit 1
fi
.venv/bin/python camera_install.py
exit $?
