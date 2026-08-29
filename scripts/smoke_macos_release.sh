#!/usr/bin/env bash
# Focused macOS release checks: sidecar boot/shutdown and DMG payload integrity.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

case "$(rustc -vV | awk '/^host:/ { print $2 }')" in
  aarch64-apple-darwin) ARCH_LABEL="arm64" ;;
  x86_64-apple-darwin) ARCH_LABEL="x64" ;;
  *) echo "Unsupported macOS host" >&2; exit 2 ;;
esac

SIDECAR="$ROOT/apps/api/dist-sidecar/storylens-api"
DMG="$ROOT/dist/release-macos-$ARCH_LABEL/StoryLens_$(tr -d '[:space:]' < VERSION)_${ARCH_LABEL}.dmg"
[[ -x "$SIDECAR" ]] || { echo "Missing executable sidecar" >&2; exit 3; }
[[ -f "$DMG" ]] || { echo "Missing DMG" >&2; exit 3; }

TMP_ROOT="$(mktemp -d)"
MOUNT_POINT="$TMP_ROOT/mount"
SIDECAR_PID=""
cleanup() {
  if [[ -n "$SIDECAR_PID" ]] && kill -0 "$SIDECAR_PID" 2>/dev/null; then
    kill "$SIDECAR_PID" 2>/dev/null || true
  fi
  if [[ -d "$MOUNT_POINT" ]]; then
    hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || \
      hdiutil detach "$MOUNT_POINT" -force -quiet 2>/dev/null || true
  fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

PORT="$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
TOKEN="storylens-macos-smoke-$PORT"
STORYLENS_APP_HOST=127.0.0.1 \
STORYLENS_APP_PORT="$PORT" \
STORYLENS_APP_ENV=production \
STORYLENS_DATA_DIR="$TMP_ROOT/data" \
STORYLENS_SHUTDOWN_TOKEN="$TOKEN" \
"$SIDECAR" >"$TMP_ROOT/sidecar.out" 2>"$TMP_ROOT/sidecar.err" &
SIDECAR_PID=$!

healthy=0
for _ in $(seq 1 120); do
  if curl --silent --fail "http://127.0.0.1:$PORT/health" >/dev/null; then
    healthy=1
    break
  fi
  if ! kill -0 "$SIDECAR_PID" 2>/dev/null; then
    cat "$TMP_ROOT/sidecar.err" >&2
    exit 4
  fi
  sleep 0.5
done
[[ "$healthy" == "1" ]] || { cat "$TMP_ROOT/sidecar.err" >&2; exit 4; }

curl --silent --fail -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:$PORT/internal/shutdown" >/dev/null
wait "$SIDECAR_PID"
SIDECAR_PID=""

mkdir -p "$MOUNT_POINT"
hdiutil attach "$DMG" -readonly -nobrowse -mountpoint "$MOUNT_POINT" -quiet
APP="$MOUNT_POINT/StoryLens.app"
[[ -d "$APP" ]] || { echo "StoryLens.app missing from DMG" >&2; exit 5; }
DESKTOP_EXECUTABLE="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist")"
[[ -n "$DESKTOP_EXECUTABLE" && -x "$APP/Contents/MacOS/$DESKTOP_EXECUTABLE" ]] || {
  echo "Desktop executable missing: $DESKTOP_EXECUTABLE" >&2
  exit 5
}
[[ -x "$APP/Contents/MacOS/storylens-api" ]] || {
  echo "Bundled sidecar missing from StoryLens.app" >&2
  find "$APP/Contents" -maxdepth 4 -type f -print >&2
  exit 5
}
codesign --verify --deep --strict --verbose=2 "$APP" || {
  echo "StoryLens.app signature verification failed" >&2
  exit 6
}
SIGNATURE_DETAILS="$(codesign -dv --verbose=4 "$APP" 2>&1)"
grep -q '^Signature=' <<<"$SIGNATURE_DETAILS" || {
  echo "StoryLens.app has no readable signature" >&2
  exit 6
}
printf '%s\n' "$SIGNATURE_DETAILS" | \
  grep -E '^(Identifier|Format|CodeDirectory|Signature|TeamIdentifier)=' || true
hdiutil detach "$MOUNT_POINT" -quiet

echo "MACOS RELEASE SMOKE OK ($ARCH_LABEL)"
