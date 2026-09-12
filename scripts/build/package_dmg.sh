#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_PATH="$DIST_DIR/ExamGrader.app"
DMG_NAME="Exam-Grader-v1.0.0-macOS-Apple-Silicon.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
TEMP_DMG_DIR="$DIST_DIR/dmg_temp"

if [ ! -d "$APP_PATH" ]; then
    echo "Error: $APP_PATH does not exist. Run build.py first."
    exit 1
fi

echo "Setting bundle version in Info.plist..."
plutil -replace CFBundleShortVersionString -string "1.0.0" "$APP_PATH/Contents/Info.plist" || true
plutil -replace CFBundleVersion -string "1.0.0" "$APP_PATH/Contents/Info.plist" || true

echo "Preparing temporary DMG folder..."
rm -rf "$TEMP_DMG_DIR" "$DMG_PATH"
mkdir -p "$TEMP_DMG_DIR"

cp -R "$APP_PATH" "$TEMP_DMG_DIR/"
ln -s /Applications "$TEMP_DMG_DIR/Applications"

echo "Creating compressed UDZO DMG..."
hdiutil create \
    -volname "Exam Grader" \
    -srcfolder "$TEMP_DMG_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

rm -rf "$TEMP_DMG_DIR"

echo "Computing SHA-256 checksum..."
shasum -a 256 "$DMG_PATH" > "$DMG_PATH.sha256"

echo "DMG created successfully:"
echo "  File: $DMG_PATH"
echo "  Size: $(du -h "$DMG_PATH" | cut -f1)"
echo "  SHA256: $(cat "$DMG_PATH.sha256")"
