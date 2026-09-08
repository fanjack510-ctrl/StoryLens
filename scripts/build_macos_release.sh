#!/usr/bin/env bash
# Build a native StoryLens macOS DMG on the current architecture.
# Run this script on macOS; PyInstaller and Tauri cannot cross-build this package from Windows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_macos_release.sh must run on macOS" >&2
  exit 2
fi

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing .venv/bin/python" >&2
  exit 2
fi

VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
ARTIFACT_SUFFIX="${STORYLENS_MACOS_ARTIFACT_SUFFIX:-}"
if [[ -n "$ARTIFACT_SUFFIX" && ! "$ARTIFACT_SUFFIX" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "Invalid macOS artifact suffix" >&2
  exit 2
fi
HOST_TRIPLE="$(rustc -vV | awk '/^host:/ { print $2 }')"
case "$HOST_TRIPLE" in
  aarch64-apple-darwin) ARCH_LABEL="arm64" ;;
  x86_64-apple-darwin) ARCH_LABEL="x64" ;;
  *) echo "Unsupported macOS Rust host: $HOST_TRIPLE" >&2; exit 2 ;;
esac

# Gatekeeper may report an unsigned Apple Silicon app downloaded from the
# internet as "damaged". Prefer a configured Developer ID, but always give
# public builds at least an ad-hoc signature.
export APPLE_SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:--}"
if [[ "$APPLE_SIGNING_IDENTITY" == "-" ]]; then
  SIGNING_MODE="adhoc"
  HARDENED_RUNTIME="false"
  export STORYLENS_PYINSTALLER_CODESIGN_IDENTITY=""
else
  SIGNING_MODE="developer-id"
  HARDENED_RUNTIME="true"
  export STORYLENS_PYINSTALLER_CODESIGN_IDENTITY="$APPLE_SIGNING_IDENTITY"
fi

echo "==> Version consistency"
"$PYTHON" scripts/version_manager.py check
if [[ "${STORYLENS_RC_CANDIDATE:-0}" != "1" ]]; then
  "$PYTHON" scripts/change_registry.py check --release
  "$PYTHON" scripts/version_manager.py release-guard
else
  echo "STORYLENS_RC_CANDIDATE=1: building an additional platform candidate for $VERSION"
fi

echo "==> Python sidecar"
"$PYTHON" scripts/check_sidecar_imports.py

rm -rf apps/api/dist-sidecar apps/api/build/pyinstaller
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath apps/api/dist-sidecar \
  --workpath apps/api/build/pyinstaller \
  apps/api/storylens-api.spec

BUILT_SIDECAR_DIR="$ROOT/apps/api/dist-sidecar/storylens-api"
BUILT_SIDECAR="$BUILT_SIDECAR_DIR/storylens-api"
if [[ ! -x "$BUILT_SIDECAR" ]]; then
  echo "Sidecar binary missing: $BUILT_SIDECAR" >&2
  exit 3
fi
git rev-parse HEAD > "$BUILT_SIDECAR_DIR/.storylens-build-id"

# PyInstaller copies the Python.org framework signature into the onedir tree,
# but the collected framework does not retain every resource covered by that
# original bundle signature. Normalize every Mach-O as an independent code
# object before verification and before Tauri places the tree in StoryLens.app.
# This also guarantees one identity across extension modules and Python itself.
while IFS= read -r -d '' MACHO_PATH; do
  if file -b "$MACHO_PATH" | grep -q 'Mach-O'; then
    if [[ "$SIGNING_MODE" == "developer-id" ]]; then
      codesign --force --options runtime --timestamp --sign "$APPLE_SIGNING_IDENTITY" "$MACHO_PATH"
    else
      codesign --force --sign - "$MACHO_PATH"
    fi
  fi
done < <(find "$BUILT_SIDECAR_DIR" -type f -print0)

"$PYTHON" scripts/check_macos_sidecar_signature.py \
  "$BUILT_SIDECAR_DIR" --signing-mode "$SIGNING_MODE"
"$PYTHON" scripts/check_sidecar_contract_current.py --write

echo "==> Frontend and Tauri DMG"
pushd apps/desktop >/dev/null
npm ci
npx vite build
if [[ "$SIGNING_MODE" == "developer-id" ]]; then
  npm run tauri -- build --bundles dmg \
    --config '{"bundle":{"macOS":{"hardenedRuntime":true}}}'
else
  npm run tauri -- build --bundles dmg
fi
popd >/dev/null

DMG_SOURCE="$(find apps/desktop/src-tauri/target/release/bundle/dmg -maxdepth 1 -type f -name '*.dmg' -print -quit)"
if [[ -z "$DMG_SOURCE" || ! -f "$DMG_SOURCE" ]]; then
  echo "DMG not found under the Tauri bundle directory" >&2
  exit 4
fi

APP_BUNDLE="$ROOT/apps/desktop/src-tauri/target/release/bundle/macos/StoryLens.app"
VERIFY_TMP=""
VERIFY_MOUNT=""
cleanup_verify_mount() {
  if [[ -n "$VERIFY_MOUNT" && -d "$VERIFY_MOUNT" ]]; then
    hdiutil detach "$VERIFY_MOUNT" -quiet 2>/dev/null || \
      hdiutil detach "$VERIFY_MOUNT" -force -quiet 2>/dev/null || true
  fi
  if [[ -n "$VERIFY_TMP" ]]; then
    rm -rf "$VERIFY_TMP"
  fi
}
trap cleanup_verify_mount EXIT

# Tauri may remove the intermediate .app after producing the DMG. In that
# case, inspect the actual application shipped in the DMG instead of treating
# the expected cleanup as a build failure.
if [[ -d "$APP_BUNDLE" ]]; then
  PACKAGED_APP="$APP_BUNDLE"
else
  VERIFY_TMP="$(mktemp -d)"
  VERIFY_MOUNT="$VERIFY_TMP/mount"
  mkdir -p "$VERIFY_MOUNT"
  hdiutil attach "$DMG_SOURCE" -readonly -nobrowse -mountpoint "$VERIFY_MOUNT" -quiet
  PACKAGED_APP="$VERIFY_MOUNT/StoryLens.app"
  if [[ ! -d "$PACKAGED_APP" ]]; then
    echo "StoryLens.app not found in generated DMG: $DMG_SOURCE" >&2
    exit 4
  fi
fi
"$PYTHON" scripts/check_macos_sidecar_signature.py \
  "$PACKAGED_APP/Contents/MacOS/storylens-api-runtime" --signing-mode "$SIGNING_MODE"
codesign --verify --deep --strict --verbose=2 "$PACKAGED_APP"
cleanup_verify_mount
trap - EXIT

RELEASE_DIR="$ROOT/dist/release-macos-$ARCH_LABEL"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

DMG_TARGET="$RELEASE_DIR/StoryLens_${VERSION}_${ARCH_LABEL}${ARTIFACT_SUFFIX:+-$ARTIFACT_SUFFIX}.dmg"
cp "$DMG_SOURCE" "$DMG_TARGET"
shasum -a 256 "$DMG_TARGET" > "$RELEASE_DIR/SHA256SUMS.txt"

DMG_TARGET="$DMG_TARGET" RELEASE_DIR="$RELEASE_DIR" VERSION="$VERSION" \
ARCH_LABEL="$ARCH_LABEL" HOST_TRIPLE="$HOST_TRIPLE" SIGNING_MODE="$SIGNING_MODE" \
HARDENED_RUNTIME="$HARDENED_RUNTIME" ARTIFACT_SUFFIX="$ARTIFACT_SUFFIX" "$PYTHON" - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

dmg = Path(os.environ["DMG_TARGET"])
summary = {
    "version": os.environ["VERSION"],
    "platform": "macos",
    "architecture": os.environ["ARCH_LABEL"],
    "target_triple": os.environ["HOST_TRIPLE"],
    "signing_mode": os.environ["SIGNING_MODE"],
    "hardened_runtime": os.environ["HARDENED_RUNTIME"] == "true",
    "sidecar_layout": "onedir",
    "artifact_suffix": os.environ["ARTIFACT_SUFFIX"],
    "signed": True,
    "notarized": False,
    "signed_and_notarized": False,
    "installer": str(dmg),
    "installer_size": dmg.stat().st_size,
    "installer_sha256": hashlib.sha256(dmg.read_bytes()).hexdigest(),
    "finished_at": datetime.now(timezone.utc).isoformat(),
}
Path(os.environ["RELEASE_DIR"], "build-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

echo "BUILD OK: $DMG_TARGET"
cat "$RELEASE_DIR/build-summary.json"
