#!/bin/sh

set -u

SOURCE_SECRET=/run/secrets/storylens_online_deepseek_api_key
RUNTIME_DIR=/run/storylens-online
STAGED_SECRET=/run/storylens-online/deepseek-api-key
STAGED_TEMP=/run/storylens-online/.deepseek-api-key.tmp
APP_IDENTITY=10001:10001

fail() {
    printf '%s\n' "Worker secret initialization failed safely." >&2
    exit 1
}

phase2b1_enabled() {
    case "${STORYLENS_ONLINE_PHASE2B1_ENABLED:-false}" in
        1 | true | TRUE | True | yes | YES | Yes | on | ON | On) return 0 ;;
        *) return 1 ;;
    esac
}

stage_provider_secret() {
    umask 077

    [ -f "$SOURCE_SECRET" ] || return 1
    [ ! -L "$SOURCE_SECRET" ] || return 1
    install -d -m 0700 -o 0 -g 0 "$RUNTIME_DIR" || return 1
    rm -f -- "$STAGED_TEMP" || return 1

    python - "$SOURCE_SECRET" "$STAGED_TEMP" <<'PY' || return 1
import os
import re
import stat
import sys

source_path, destination_path = sys.argv[1:]
source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
source_fd = os.open(source_path, source_flags)
try:
    if not stat.S_ISREG(os.fstat(source_fd).st_mode):
        raise ValueError
    data = os.read(source_fd, 4097)
    if os.read(source_fd, 1):
        raise ValueError
finally:
    os.close(source_fd)

if not data or b"\x00" in data or b"\r" in data or b"\n" in data:
    raise ValueError
if any(chr(byte).isspace() for byte in data):
    raise ValueError
if re.fullmatch(rb"sk-[A-Za-z0-9_-]{16,256}", data) is None:
    raise ValueError

destination_flags = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
destination_fd = os.open(destination_path, destination_flags, 0o600)
with os.fdopen(destination_fd, "wb") as destination:
    destination.write(data)
    destination.flush()
    os.fsync(destination.fileno())
PY

    chown "$APP_IDENTITY" "$STAGED_TEMP" || return 1
    chmod 0400 "$STAGED_TEMP" || return 1
    mv -f -- "$STAGED_TEMP" "$STAGED_SECRET" || return 1
    chown "$APP_IDENTITY" "$RUNTIME_DIR" || return 1
    chmod 0700 "$RUNTIME_DIR" || return 1
}

if phase2b1_enabled; then
    stage_provider_secret >/dev/null 2>&1 || fail
fi

[ "$#" -gt 0 ] || fail
runner=$(command -v gosu 2>/dev/null) || fail
"$runner" "$APP_IDENTITY" true >/dev/null 2>&1 || fail
exec "$runner" "$APP_IDENTITY" "$@"
