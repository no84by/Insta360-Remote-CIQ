#!/bin/zsh
# Insta360 X5 Remote - macOS installer. Double-click, then plug in the watch when asked.
# This file only finds Python 3.8 or newer and starts install.py (without it: python3 install.py).
# If Python is missing it can download the official python.org installer and open it; you
# approve and finish that installer yourself.
cd "$(dirname "$0")" || exit 1
PY_PKG="https://www.python.org/ftp/python/3.13.16/python-3.13.16-macos11.pkg"

ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; }

find_python() {
  PY=""
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    [[ -x $c ]] && ok "$c" && { PY=$c; return; }
  done
  # /usr/bin/python3 only runs once Apple's command line tools are installed; otherwise it
  # opens an installer dialog instead.
  xcode-select -p >/dev/null 2>&1 && [[ -x /usr/bin/python3 ]] && ok /usr/bin/python3 && PY=/usr/bin/python3
}

find_python
if [[ -z $PY ]]; then
  echo "The installer needs Python 3, which is not installed on this Mac."
  echo "Python is free; the official installer comes from python.org (about 70 MB)."
  if read -q "?Download and open the Python installer now? [y/N] "; then
    echo
    pkg="$(mktemp -d)/python-installer.pkg"
    if curl -fL --progress-bar -o "$pkg" "$PY_PKG" &&
       sig="$(pkgutil --check-signature "$pkg")" &&
       grep -q "Status: signed by a developer certificate issued by Apple for distribution" <<<"$sig" &&
       grep -q "Python Software Foundation" <<<"$sig"; then
      open "$pkg"
      echo "Click through the Python installer window (it asks for your Mac password)."
      echo "Waiting for it to finish..."
      for i in {1..900}; do
        find_python
        [[ -n $PY ]] && ! pgrep -xq Installer && break
        sleep 1
      done
    else
      echo "Download failed or the file is not validly signed by the Python Software Foundation."
    fi
  fi
  echo
fi

if [[ -n $PY ]]; then
  "$PY" install.py "$@"
else
  echo "Python is still not installed. Get it from https://www.python.org/downloads/macos/"
  echo "and then double-click this file again."
fi
if [[ -t 0 ]]; then
  echo
  read -k1 "?Press any key to close this window."
  echo
fi
