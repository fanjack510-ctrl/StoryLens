#!/bin/sh
set -eu

# This trusted entrypoint must first be installed by a manually approved FULL
# deployment. Never extract/execute a script received in an unchecked bundle.
if [ "$#" -ne 6 ] || [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'DEPLOY_PREFLIGHT_FAILED' >&2
    exit 1
fi
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONPATH PYTHONHOME
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 -I -B "$SCRIPT_DIR/deploy_runtime.py" "$@"
