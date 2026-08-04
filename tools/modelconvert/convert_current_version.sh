#!/bin/bash
#
# convert_current_version.sh — convert the current version of a .xcdatamodeld
# from the legacy binary format (elements/layout files) to the modern XML
# format (a single `contents` file), with full verification.
#
# Usage:
#   ./convert_current_version.sh <path/to/Model.xcdatamodeld> [--install]
#
# Without --install, runs the conversion and verification in a temp directory
# and reports the result without touching the model. With --install, replaces
# the current version's binary files with the verified XML and re-verifies the
# real bundle.
#
set -euo pipefail

MODELD="${1:?usage: convert_current_version.sh <Model.xcdatamodeld> [--install]}"
INSTALL="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

MOMC="${MOMC:-/Applications/Xcode.app/Contents/Developer/usr/bin/momc}"
[ -x "$MOMC" ] || { echo "momc not found at $MOMC (set MOMC env var)"; exit 1; }

# Which version is current?
CURRENT=$(/usr/libexec/PlistBuddy -c "Print _XCCurrentVersionName" "$MODELD/.xccurrentversion")
CURRENT_BASE="${CURRENT%.xcdatamodel}"
echo "Current model version: $CURRENT"

if [ -f "$MODELD/$CURRENT/contents" ]; then
    echo "Current version is already in XML format ($MODELD/$CURRENT/contents). Nothing to do."
    exit 0
fi

WORK=$(mktemp -d)
echo "Working directory: $WORK"

# 1. Compile the untouched bundle as the baseline.
"$MOMC" "$MODELD" "$WORK/orig.momd" > /dev/null
cp "$WORK/orig.momd/$CURRENT_BASE.mom" "$WORK/original-current.mom"

# 2. Convert the compiled current version to XML source.
swift "$SCRIPT_DIR/convert_mom_to_xml.swift" "$WORK/original-current.mom" "$WORK/contents"

# 3. Build a candidate bundle with the XML replacing the current version, and compile it.
cp -R "$MODELD" "$WORK/candidate.xcdatamodeld"
rm -f "$WORK/candidate.xcdatamodeld/$CURRENT/elements" "$WORK/candidate.xcdatamodeld/$CURRENT/layout"
cp "$WORK/contents" "$WORK/candidate.xcdatamodeld/$CURRENT/contents"
"$MOMC" "$WORK/candidate.xcdatamodeld" "$WORK/candidate.momd" > /dev/null

# 4. Verify the converted current version against the original.
echo "--- Verifying converted current version against original ---"
swift "$SCRIPT_DIR/verify_models.swift" "$WORK/original-current.mom" "$WORK/candidate.momd/$CURRENT_BASE.mom"

# 5. Verify every other (historical) version compiled byte-identically.
echo "--- Verifying historical versions are unaffected ---"
for mom in "$WORK/orig.momd/"*.mom; do
    base=$(basename "$mom")
    [ "$base" = "$CURRENT_BASE.mom" ] && continue
    if ! cmp -s "$mom" "$WORK/candidate.momd/$base"; then
        echo "FAIL: $base differs between baseline and candidate compile"
        exit 1
    fi
done
echo "PASS: all historical version .mom files are byte-identical"

if [ "$INSTALL" != "--install" ]; then
    echo ""
    echo "Dry run complete. Generated XML: $WORK/contents"
    echo "Re-run with --install to replace $MODELD/$CURRENT with the XML version."
    exit 0
fi

# 6. Install: swap the verified XML into the real bundle, then re-verify from disk.
cp "$MODELD/$CURRENT/elements" "$WORK/original-elements.backup"
cp "$WORK/contents" "$MODELD/$CURRENT/contents"
rm "$MODELD/$CURRENT/elements"
[ -f "$MODELD/$CURRENT/layout" ] && rm "$MODELD/$CURRENT/layout"

"$MOMC" "$MODELD" "$WORK/final.momd" > /dev/null
echo "--- Re-verifying installed bundle ---"
swift "$SCRIPT_DIR/verify_models.swift" "$WORK/original-current.mom" "$WORK/final.momd/$CURRENT_BASE.mom"
echo ""
echo "Installed. $MODELD/$CURRENT is now in XML format (contents file)."
echo "Backup of the original binary file: $WORK/original-elements.backup"
