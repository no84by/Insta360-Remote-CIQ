#!/bin/sh
# Release asset: zip installer/ (launchers, install.py, READ ME FIRST.txt; no tests) as
# dist/x5-remote-installer.zip, with the files in an x5-remote-installer/ folder. The zip keeps
# the executable bits of the Mac and Linux launchers. Usage: tools/installer-zip.sh
set -e
cd "$(dirname "$0")/.."
out="$PWD/dist/x5-remote-installer.zip"
stage=$(mktemp -d)
mkdir -p dist "$stage/x5-remote-installer"
cp installer/install.py "installer/READ ME FIRST.txt" "installer/Install on Windows.bat" \
   "installer/Install on Mac.command" "installer/Install on Linux.sh" LICENSE "$stage/x5-remote-installer/"
chmod 755 "$stage/x5-remote-installer/Install on Mac.command" "$stage/x5-remote-installer/Install on Linux.sh"
rm -f "$out"
(cd "$stage" && zip -q -r -X "$out" x5-remote-installer)
rm -rf "$stage"
echo "$out"
