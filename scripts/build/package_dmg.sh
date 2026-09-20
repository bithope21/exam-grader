#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_PATH="$DIST_DIR/ExamGrader.app"
DMG_NAME="Exam-Grader-v1.1.0-macOS-Apple-Silicon.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
VOLUME_NAME="Exam Grader"
TEMP_DMG_DIR="$DIST_DIR/dmg_temp"

if [ ! -d "$APP_PATH" ]; then
    echo "Error: $APP_PATH does not exist. Run build.py first."
    exit 1
fi

echo "==> Preparing Info.plist versioning..."
plutil -replace CFBundleShortVersionString -string "1.1.0" "$APP_PATH/Contents/Info.plist" || true
plutil -replace CFBundleVersion -string "1.1.0" "$APP_PATH/Contents/Info.plist" || true
# Versioning changes the bundle metadata after PyInstaller's initial signing.
# Re-sign the final app before it is copied into the DMG.
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"

echo "Preparing temporary DMG folder..."
rm -rf "$TEMP_DMG_DIR" "$DMG_PATH"
mkdir -p "$TEMP_DMG_DIR"

cp -R "$APP_PATH" "$TEMP_DMG_DIR/"
ln -s /Applications "$TEMP_DMG_DIR/Applications"

if [ -f "$ROOT_DIR/resources/icons/icon.icns" ]; then
    cp "$ROOT_DIR/resources/icons/icon.icns" "$TEMP_DMG_DIR/.VolumeIcon.icns"
    SetFile -c icnC "$TEMP_DMG_DIR/.VolumeIcon.icns" 2>/dev/null || true
    SetFile -a C "$TEMP_DMG_DIR" 2>/dev/null || true
fi

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
