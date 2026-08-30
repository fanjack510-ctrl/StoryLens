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
  export STORYLENS_PYINSTALLER_CODESIGN_IDENTITY=""
else
  SIGNING_MODE="developer-id"
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

# actions/setup-python supplies a Python.org framework that carries the Python
# team's signature. PyInstaller onefile embeds that framework, while Tauri
# later re-signs the outer sidecar. On downloaded Apple Silicon apps, macOS
# Library Validation rejects that mixed-Team pair. For public ad-hoc builds,
# normalize the source framework binary to the same ad-hoc identity before it
# enters the onefile archive. Developer ID builds are signed consistently by
# PyInstaller via STORYLENS_PYINSTALLER_CODESIGN_IDENTITY instead.
if [[ "$SIGNING_MODE" == "adhoc" ]]; then
  PYTHON_SHARED="$("$PYTHON" -c 'import sys; from pathlib import Path; print(Path(sys.base_prefix) / "Python")')"
  if [[ ! -f "$PYTHON_SHARED" ]]; then
    echo "Python framework shared library not found: $PYTHON_SHARED" >&2
    exit 3
  fi
  if [[ -w "$PYTHON_SHARED" ]]; then
    codesign --force --sign - "$PYTHON_SHARED"
  else
    sudo codesign --force --sign - "$PYTHON_SHARED"
  fi
  codesign --verify --strict --verbose=2 "$PYTHON_SHARED"
  "$PYTHON" -c 'import sys; print(sys.version)'
fi

rm -rf apps/api/dist-sidecar apps/api/build/pyinstaller
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath apps/api/dist-sidecar \
  --workpath apps/api/build/pyinstaller \
  apps/api/storylens-api.spec

BUILT_SIDECAR="$ROOT/apps/api/dist-sidecar/storylens-api"
if [[ ! -x "$BUILT_SIDECAR" ]]; then
  echo "Sidecar binary missing: $BUILT_SIDECAR" >&2
  exit 3
fi
"$PYTHON" scripts/check_macos_sidecar_signature.py \
  "$BUILT_SIDECAR" --signing-mode "$SIGNING_MODE"
"$PYTHON" scripts/check_sidecar_contract_current.py --write

BIN_DIR="$ROOT/apps/desktop/src-tauri/binaries"
mkdir -p "$BIN_DIR"
TAURI_SIDECAR="$BIN_DIR/storylens-api-$HOST_TRIPLE"
cp "$BUILT_SIDECAR" "$TAURI_SIDECAR"
chmod 755 "$TAURI_SIDECAR"

echo "==> Frontend and Tauri DMG"
pushd apps/desktop >/dev/null
npm ci
npx vite build
npm run tauri -- build --bundles dmg
popd >/dev/null

APP_BUNDLE="$ROOT/apps/desktop/src-tauri/target/release/bundle/macos/StoryLens.app"
if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "App bundle not found after Tauri build: $APP_BUNDLE" >&2
  exit 4
fi
"$PYTHON" scripts/check_macos_sidecar_signature.py \
  "$APP_BUNDLE/Contents/MacOS/storylens-api" --signing-mode "$SIGNING_MODE"
codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"

RELEASE_DIR="$ROOT/dist/release-macos-$ARCH_LABEL"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

DMG_SOURCE="$(find apps/desktop/src-tauri/target/release/bundle/dmg -maxdepth 1 -type f -name '*.dmg' -print -quit)"
if [[ -z "$DMG_SOURCE" || ! -f "$DMG_SOURCE" ]]; then
  echo "DMG not found under the Tauri bundle directory" >&2
  exit 4
fi

DMG_TARGET="$RELEASE_DIR/StoryLens_${VERSION}_${ARCH_LABEL}.dmg"
cp "$DMG_SOURCE" "$DMG_TARGET"
shasum -a 256 "$DMG_TARGET" > "$RELEASE_DIR/SHA256SUMS.txt"

DMG_TARGET="$DMG_TARGET" RELEASE_DIR="$RELEASE_DIR" VERSION="$VERSION" \
ARCH_LABEL="$ARCH_LABEL" HOST_TRIPLE="$HOST_TRIPLE" SIGNING_MODE="$SIGNING_MODE" "$PYTHON" - <<'PY'
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
