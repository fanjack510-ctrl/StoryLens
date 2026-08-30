#!/bin/sh

set -eu

PB_BIN=${POCKETBASE_BINARY:-/pb/pocketbase}
PB_DATA_DIR=${POCKETBASE_DATA_DIR:-/pb/pb_data}
PB_MIGRATIONS_DIR=${POCKETBASE_MIGRATIONS_DIR:-/pb/pb_migrations}
PB_EMAIL_FILE=${POCKETBASE_SUPERUSER_EMAIL_FILE:-/run/secrets/pocketbase_superuser_email}
PB_PASSWORD_FILE=${POCKETBASE_SUPERUSER_PASSWORD_FILE:-/run/secrets/pocketbase_superuser_password}
PB_RUNNER=${POCKETBASE_RUNNER-/sbin/su-exec}

fail() {
    printf '%s\n' "PocketBase initialization failed safely." >&2
    exit 1
}

read_secret() {
    secret_file=$1
    if [ ! -f "$secret_file" ] || [ ! -r "$secret_file" ]; then
        fail
    fi

    secret_value=$(cat "$secret_file" 2>/dev/null) || fail
    carriage_return=$(printf '\r')
    case "$secret_value" in
        *"$carriage_return") secret_value=${secret_value%"$carriage_return"} ;;
    esac
    case "$secret_value" in
        *'
'*|*"$carriage_return"*) fail ;;
    esac
    if [ -z "$secret_value" ]; then
        fail
    fi
    printf '%s' "$secret_value"
}

run_pocketbase() {
    if [ -n "$PB_RUNNER" ]; then
        "$PB_RUNNER" pocketbase:pocketbase "$PB_BIN" "$@"
    else
        "$PB_BIN" "$@"
    fi
}

email=$(read_secret "$PB_EMAIL_FILE")
password=$(read_secret "$PB_PASSWORD_FILE")

if ! printf '%s\n' "$email" | grep -Eq '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'; then
    fail
fi

# PocketBase requires at least 8 characters. Production documentation requires
# operators to generate a much stronger random value of at least 32 characters.
if [ "${#password}" -lt 8 ]; then
    fail
fi

if ! run_pocketbase migrate up \
    --dir="$PB_DATA_DIR" \
    --migrationsDir="$PB_MIGRATIONS_DIR" \
    --dev=false >/dev/null 2>&1; then
    fail
fi

if ! run_pocketbase superuser upsert "$email" "$password" \
    --dir="$PB_DATA_DIR" \
    --migrationsDir="$PB_MIGRATIONS_DIR" \
    --dev=false >/dev/null 2>&1; then
    fail
fi

printf '%s\n' "PocketBase initialization completed safely."
