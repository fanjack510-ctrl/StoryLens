# StoryLens Online — Hong Kong Beta Phase 2A

This stack is isolated from the packaged StoryLens 1.3.6 desktop runtime. Phase
2A provides one deliberately small online chain:

`register/login -> upload TXT -> enqueue -> local worker -> poll -> view result`

The worker only calculates deterministic text statistics. It does not call an
AI provider, reserve or deduct wallet funds, write a model-usage ledger entry,
or contact Afdian. A result identifies itself as `phase2a_smoke`,
`real_ai_analysis: false`, `billing_status: not_billable`, and
`charged_cny: 0`.

## Architecture and public boundary

- Caddy is the only public service and exposes ports 80/443.
- `/health/*` and `/api/*` are proxied to FastAPI; all other paths go to the
  internal React web service.
- FastAPI is a BFF for the private PocketBase service. The browser receives
  only an `HttpOnly; Secure; SameSite=Lax` session cookie and never receives or
  stores an administrator credential.
- PostgreSQL, Redis, PocketBase, the API, worker, and web containers have no
  published ports. PocketBase administration remains server-local.
- `pocketbase-init` is a one-shot, networkless service. It alone receives the
  two file-backed superuser secrets, applies migrations, and idempotently
  upserts the server-internal superuser before the long-running PocketBase
  service is allowed to start. API, worker, web, gateway, and PocketBase itself
  never mount those secrets.
- API and worker share the persistent `online_uploads` volume. Existing
  `pocketbase_data`, `postgres_data`, and `redis_data` volumes are unchanged.
- Redis uses a pending list plus an in-flight list. A worker acknowledges a job
  only after processing; startup recovers unacknowledged jobs. PostgreSQL
  compare-and-update claims, leases, and terminal-state checks make duplicate
  delivery safe for the single-worker Phase 2A deployment.
- A blocking empty-queue poll is normal. The worker uses a socket read timeout
  with explicit safety margin, treats residual Redis timeouts/disconnects as
  transient, resets the connection pool, recovers the in-flight list, and
  retries with bounded exponential backoff. Only the first failure in an outage
  is logged; a later successful Redis command logs recovery.

The PocketBase image contains version-controlled JavaScript migrations in
`/pb/pb_migrations`. Only `pb_data` is mounted, so the persistent data volume
does not hide migrations packaged in a newer image. The init service runs
`migrate up` and then the PocketBase 0.40.1 `superuser upsert` command against
that same volume. `serve` starts only after both commands succeed. This avoids
the first-run installer URL and its short-lived token at the source.

## Server prerequisites

- Hong Kong x86_64 Linux host (Ubuntu 22.04 LTS recommended)
- Docker Engine and Docker Compose v2
- a domain A/AAAA record pointing to the host
- inbound TCP 80/443 only

## Configure

```bash
cd infra/online
cp .env.example online.env
chmod 600 online.env
```

Replace every placeholder in `online.env`. Secrets stay on the server only. The
desktop provider configuration, local database, licence data, and API keys are
not read or copied by this stack. `UPLOAD_MAX_BYTES` is non-secret and defaults
to 10485760 (10 MiB).

### Provision the internal PocketBase superuser secrets

Create the secret directory and files without putting either value in shell
history. The internal email is entered with `sudoedit`; generate a random
password of at least 32 characters directly into its file:

```bash
sudo install -d -m 700 -o root -g root /opt/storylens/shared/secrets
sudo install -m 600 -o root -g root /dev/null \
  /opt/storylens/shared/secrets/pocketbase-superuser-email
sudoedit /opt/storylens/shared/secrets/pocketbase-superuser-email
sudo sh -c 'umask 077; openssl rand -base64 48 | tr -d "\n" > /opt/storylens/shared/secrets/pocketbase-superuser-password'
sudo chown root:root \
  /opt/storylens/shared/secrets/pocketbase-superuser-email \
  /opt/storylens/shared/secrets/pocketbase-superuser-password
sudo chmod 600 \
  /opt/storylens/shared/secrets/pocketbase-superuser-email \
  /opt/storylens/shared/secrets/pocketbase-superuser-password
```

Run the deployment commands from a root shell, or prefix `docker compose` with
`sudo`, because a non-root Compose client cannot read `root:root 600` file
sources. The secret contents are still mounted only into `pocketbase-init`.

Do not paste either value into Codex, chat, tickets, Git, Compose YAML, or an
environment variable. `online.env` contains paths only:

```dotenv
POCKETBASE_SUPERUSER_EMAIL_FILE=/opt/storylens/shared/secrets/pocketbase-superuser-email
POCKETBASE_SUPERUSER_PASSWORD_FILE=/opt/storylens/shared/secrets/pocketbase-superuser-password
```

Compose file-backed secrets preserve the host file ownership on this runtime,
so the init shell starts as root only to read the `root:root 600` files. It uses
`su-exec` to run every PocketBase database command as the image's unprivileged
`pocketbase` user. The long-running service also remains unprivileged and never
receives the secret mounts.

Worker Redis timing is also non-secret. The defaults are a 5-second blocking
poll, a 15-second socket read timeout, a 5-second connect timeout, and bounded
retry delays from 1 to 15 seconds. Startup validation requires the socket read
timeout to exceed the blocking poll by at least 2 seconds and requires the
maximum retry delay to be no smaller than the initial delay. Invalid timing
combinations stop the worker before it connects and never print the Redis URL.

## Validate and start

```bash
docker compose --env-file online.env config --quiet
docker compose --env-file online.env build
docker compose --env-file online.env stop gateway online-api online-worker pocketbase
docker compose --env-file online.env run --rm pocketbase-init
docker compose --env-file online.env up -d
docker compose --env-file online.env ps
curl https://YOUR_DOMAIN/health/live
curl https://YOUR_DOMAIN/health/ready
```

`pocketbase-init` prints only `PocketBase initialization completed safely.` on
success. Missing, empty, malformed, or unreadable secrets, migration failures,
and upsert failures all return nonzero with a fixed message. PocketBase depends
on the init service with `service_completed_successfully`, so a fresh failed
init prevents `serve` and therefore cannot produce an installer token.

Confirm rendered Compose and the created init container do not contain either
secret value without printing the configuration or the values:

```bash
docker compose --env-file online.env config | sudo python3 -c '
import pathlib, sys
config = sys.stdin.read()
paths = [
    pathlib.Path("/opt/storylens/shared/secrets/pocketbase-superuser-email"),
    pathlib.Path("/opt/storylens/shared/secrets/pocketbase-superuser-password"),
]
raise SystemExit(1 if any(p.read_text().rstrip("\r\n") in config for p in paths) else 0)
'

init_id="$(docker compose --env-file online.env ps -aq pocketbase-init)"
docker inspect "$init_id" | sudo python3 -c '
import pathlib, sys
inspection = sys.stdin.read()
paths = [
    pathlib.Path("/opt/storylens/shared/secrets/pocketbase-superuser-email"),
    pathlib.Path("/opt/storylens/shared/secrets/pocketbase-superuser-password"),
]
raise SystemExit(1 if any(p.read_text().rstrip("\r\n") in inspection for p in paths) else 0)
'
```

Verify PocketBase logs contain no installer route or JWT-like value. `grep -q`
returns only a status and does not print a matching line:

```bash
if docker compose --env-file online.env logs --no-color pocketbase | \
  grep -Eqi 'pbinstall|/_/#/|eyJ[A-Za-z0-9_-]{10,}'; then
  echo 'PocketBase log safety check failed.' >&2
  exit 1
fi
```

After PostgreSQL is healthy, both application roles first run
`python -m storylens_online.db.init_schema`. The initializer creates all seven
currently registered `online_` tables with SQLAlchemy `metadata.create_all`, is
safe to repeat, and never drops or truncates data. Uvicorn or the worker starts
only after initialization succeeds.

The same check can be run explicitly:

```bash
docker compose --env-file online.env run --rm online-api \
  python -m storylens_online.db.init_schema
```

Before formal Phase 2A acceptance, run an isolated real-Redis worker smoke test:

1. Start with the pending and processing queues empty.
2. Observe the worker for at least three complete poll periods.
3. Confirm its container restart count does not increase.
4. Confirm logs contain no `Timeout reading from socket`.
5. Enqueue one isolated smoke job and confirm the worker consumes it
   successfully.

This smoke test is a deployment gate, not evidence that may be inferred from
Fake Redis tests. It must be repeated in the Hong Kong isolated environment by
the operator before Phase 2A is accepted.

This creates missing PostgreSQL tables only. PocketBase owns only its auth
collection migration and is never responsible for StoryLens Online SQL schema.
Future changes to existing columns still require a versioned SQL migration.

`/health/ready` continues to report `afdian_not_configured` when no Afdian
credential is supplied. That is expected in Phase 2A and does not imply that
the no-charge smoke worker uses Afdian.

## Future Hong Kong upgrade procedure

Do these steps only during an approved deployment window:

1. Record the deployed commit and back up PostgreSQL, PocketBase `pb_data`, and
   the `online_uploads` volume outside the server.
2. Fetch and check out the approved commit without changing `online.env` or the
   two root-owned secret files.
3. Run `docker compose --env-file online.env config --quiet` and build.
4. Stop gateway, API, worker, and PocketBase so the one-shot CLI has exclusive
   access to `pb_data`.
5. Run `docker compose --env-file online.env run --rm pocketbase-init`. Continue
   only after the fixed success message and zero exit status.
6. Run `docker compose --env-file online.env up -d`; do not add `-v`, because
   named volumes must be preserved.
7. Run the non-printing Compose/inspect and PocketBase log safety checks above.
8. Confirm container health, both health endpoints, registration/login,
   one non-sensitive TXT smoke task, and that only 80/443 are public.

### Rotate the internal superuser password

Stop PocketBase and its consumers, replace only the password file without
printing it, rerun the init, and then start the stack:

```bash
docker compose --env-file online.env stop gateway online-api online-worker pocketbase
sudo sh -c 'umask 077; openssl rand -base64 48 | tr -d "\n" > /opt/storylens/shared/secrets/pocketbase-superuser-password'
sudo chown root:root /opt/storylens/shared/secrets/pocketbase-superuser-password
sudo chmod 600 /opt/storylens/shared/secrets/pocketbase-superuser-password
docker compose --env-file online.env run --rm pocketbase-init
docker compose --env-file online.env up -d
```

`superuser upsert` updates the existing record selected by email; it does not
create a duplicate administrator. Never rotate by adding credentials to a
Compose command, environment variable, or migration.

## Rollback procedure

1. Preserve logs and take another database/upload snapshot before rollback.
2. Check out the previously recorded approved commit. Do not start a vulnerable
   PocketBase definition against a fresh volume with no superuser; retain this
   fixed init step or run it successfully before starting the older service.
3. Rebuild and run with `--env-file online.env` without deleting named volumes.
4. Verify the log safety check, health, and login. If the older application cannot read an additive
   schema change, stop application traffic and restore the matching pre-upgrade
   backups as a coordinated data rollback.

Do not run `docker compose down -v`, delete volumes, or manually remove the two
Phase 2A tables as a rollback shortcut.

## Security and operating boundaries

- Never commit `.env`, `online.env`, database dumps, PocketBase data, upload contents, or
  tokens.
- Never copy the internal PocketBase email or password into Git, chat, support
  tickets, test output, image layers, Compose commands, or browser code.
- Do not publish ports 5432, 6379, 8090, or either internal 8080 service.
- Uploaded content and original text are not logged. Public errors contain
  stable codes rather than exception stacks or internal connection details.
- Uploads accept non-empty UTF-8/UTF-8-SIG `.txt` only, use server-generated
  storage keys, enforce the configured size limit, and persist SHA-256.
- Every upload, job, and result query is scoped to the authenticated PocketBase
  user ID to prevent cross-user access.
- Phase 2A is not the formal public Beta: real whole-book analysis, model APIs,
  x2 billing, Afdian recharge, and public onboarding remain out of scope.
