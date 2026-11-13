#!/usr/bin/env bash
# Insta360 X5 Remote - Linux installer. Run it (or double-click and choose "Run in terminal"),
# then plug in the watch when asked. This file only finds Python 3.8 or newer and starts
# install.py (without it: python3 install.py).
cd "$(dirname "$0")" || exit 1

ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; }

PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 && ok "$c" && { PY=$c; break; }
done

if [[ -z $PY ]]; then
  echo "The installer needs Python 3, which is not installed."
  echo "Install it with your package manager, for example:"
  echo "  Fedora:          sudo dnf install python3"
  echo "  Debian/Ubuntu:   sudo apt install python3"
  echo "  Arch:            sudo pacman -S python"
  echo "then start this file again."
else
  "$PY" install.py "$@"
fi
if [[ -t 0 ]]; then
  echo
  read -r -n1 -p "Press any key to close this window."
  echo
fi
