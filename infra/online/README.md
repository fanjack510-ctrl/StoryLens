# StoryLens Online — Hong Kong Beta Phase 2A / internal Phase 2B1 gate

This stack is isolated from the packaged StoryLens 1.3.6 desktop runtime. Phase
2A provides one deliberately small online chain:

`register/login -> upload TXT -> enqueue -> local worker -> poll -> view result`

The default `phase2a_smoke` worker path only calculates deterministic text
statistics. It does not call an AI provider, reserve or deduct wallet funds,
write a model-usage ledger entry, or contact Afdian. A result identifies itself as `phase2a_smoke`,
`real_ai_analysis: false`, `billing_status: not_billable`, and
`charged_cny: 0`.

Phase 2B1 adds a separate, default-off internal gate for one controlled TXT
analysis through a fixed Worker-only DeepSeek provider. Only allowlisted users
can reach that path. It records internal model usage and provider cost, but it
still never charges a wallet: `billing_status` remains `not_billable` and
`charged_cny` remains zero.

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

### Provision the Phase 2B1 Worker-only Provider secret

The provider credential is a Docker file-backed secret named
`storylens_online_deepseek_api_key`. Only `online-worker` mounts it. The
API, web, gateway, PocketBase, init service, images, build arguments, rendered
Compose configuration, and application environment never receive the key.

On the Hong Kong Docker Compose runtime, a local file-backed Secret preserves
the host file's `root:root 600` ownership; Compose `uid`/`gid`/`mode` metadata
cannot remap that bind-mounted inode for the non-root Worker. The Worker
therefore has a dedicated entrypoint that starts as root only long enough to
validate the source and copy its exact bytes into the container-local
`/run/storylens-online` tmpfs. The tmpfs is `noexec,nosuid,nodev`, limited to
64 KiB, and disappears with the container. Its directory becomes
`0700:10001:10001` and the copied `deepseek-api-key` becomes
`0400:10001:10001`; the original remains `0600:0:0`. The entrypoint then uses
`gosu` and `exec` to run database initialization and the Worker as the existing
non-root `storylens` identity (`10001:10001`), including PID 1. The API never
uses this root entrypoint and keeps the image's default non-root user.

When `PHASE2B1_ENABLED=false`, the entrypoint does not stat, read, validate, or
copy the Provider Secret; it only drops privileges and starts the unchanged
Worker path. When enabled, a missing, non-regular, empty, multiline, whitespace-
containing, NUL-containing, malformed, or unstaggable key fails before schema
initialization and the task loop. The only permitted initialization error is
`Worker secret initialization failed safely.`; it contains no path, key,
length, prefix, digest, or underlying command output.

Create the file directly on the server without placing the key in shell
history. The fixed prompt below reads it without terminal echo and writes no
trailing newline (the entrypoint deliberately rejects CR/LF and whitespace).
Keep the global gate disabled and the allowlist empty until isolated acceptance
is approved:

```bash
sudo install -m 600 -o root -g root /dev/null \
  /opt/storylens/shared/secrets/deepseek-api-key
sudo python3 - <<'PY'
import getpass
import os
import re

path = "/opt/storylens/shared/secrets/deepseek-api-key"
value = getpass.getpass("DeepSeek API Key: ").encode("ascii")
if re.fullmatch(rb"sk-[A-Za-z0-9_-]{16,256}", value) is None:
    raise SystemExit("Invalid DeepSeek API Key format.")
descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC)
with os.fdopen(descriptor, "wb") as secret_file:
    secret_file.write(value)
    secret_file.flush()
    os.fsync(secret_file.fileno())
PY
sudo chown root:root /opt/storylens/shared/secrets/deepseek-api-key
sudo chmod 600 /opt/storylens/shared/secrets/deepseek-api-key
```

`online.env` contains only the host path and non-secret policy values:

```dotenv
PHASE2B1_ENABLED=false
PHASE2B1_ALLOWLISTED_USER_IDS=
PHASE2B1_API_KEY_FILE=/opt/storylens/shared/secrets/deepseek-api-key
```

The provider base URL is frozen to the exact HTTPS origin
`https://api.deepseek.com`; the Worker posts only to `/chat/completions` and
never follows redirects. User info, explicit ports, paths on the configured
origin, query strings, fragments, browser-selected providers, URLs, models,
thinking parameters, pricing, or exchange rates are rejected. The fixed model
uses non-thinking, non-streaming JSON Object mode with a 2,048-token output
limit. Worker request and retry timing must fit inside its lease with a
30-second safety margin or startup validation fails closed.

Every HTTP attempt freezes its own Decimal price snapshot from the UTC
`request_sent_at`. Monday-Friday 01:00-04:00 and 06:00-10:00 UTC are peak
intervals (left-closed, right-open): cache hit/miss/output cost
`0.014/0.44/1.32 USD` per million Token. All other times use
`0.007/0.22/0.66 USD`. The fixed conversion is `1 USD = 6.7811 CNY` under
`safe-usdcny-central-parity-2026-08-28`; the per-task Provider cap is `0.50 CNY`.
These values are code-frozen and are not accepted from browser or API payloads.

Before enabling the gate, confirm the mount boundary without printing its value:

```bash
docker compose --env-file online.env config | grep -q 'storylens_online_deepseek_api_key'
worker_id="$(docker compose --env-file online.env ps -q online-worker)"
docker inspect "$worker_id" | grep -q '/run/secrets/storylens_online_deepseek_api_key'
for service in gateway online-api online-web pocketbase pocketbase-init; do
  service_id="$(docker compose --env-file online.env ps -aq "$service")"
  if [ -n "$service_id" ] && docker inspect "$service_id" | \
    grep -q '/run/secrets/storylens_online_deepseek_api_key'; then
    echo "Provider secret boundary failed for $service" >&2
    exit 1
  fi
done
```

After starting an isolated Worker with the gate enabled, verify source and
tmpfs permissions, read boundaries, tmpfs restrictions, and the final PID 1
identity without reading the key to stdout:

```bash
worker_id="$(docker compose --env-file online.env ps -q online-worker)"
api_id="$(docker compose --env-file online.env ps -q online-api)"

test "$(docker exec -u 0 "$worker_id" stat -c '%a:%u:%g' \
  /run/secrets/storylens_online_deepseek_api_key)" = "600:0:0"
test "$(docker exec -u 0 "$worker_id" stat -c '%a:%u:%g' \
  /run/storylens-online/deepseek-api-key)" = "400:10001:10001"
docker exec -u 10001:10001 "$worker_id" sh -c \
  'test -r /run/storylens-online/deepseek-api-key && ! test -r /run/secrets/storylens_online_deepseek_api_key'
docker exec -u 0 "$worker_id" awk \
  '$1 == "Uid:" { exit !($2 == 10001 && $3 == 10001 && $4 == 10001 && $5 == 10001) }' \
  /proc/1/status
docker inspect "$worker_id" | python3 -c '
import json, sys
tmpfs = json.load(sys.stdin)[0]["HostConfig"]["Tmpfs"]
options = set(tmpfs["/run/storylens-online"].split(","))
required = {"rw", "noexec", "nosuid", "nodev"}
size_ok = bool({"size=64k", "size=65536"} & options)
mode_ok = bool({"mode=0700", "mode=700", "mode=448"} & options)
raise SystemExit(0 if required <= options and size_ok and mode_ok else 1)
'
test "$(docker inspect "$worker_id" --format '{{json .Config.Entrypoint}}')" = \
  '["/usr/local/bin/storylens-online-worker-entrypoint"]'
test "$(docker inspect "$api_id" --format '{{json .Config.Entrypoint}}')" = 'null'
```

For the required real-value leak scan, keep the comparison entirely inside a
root-only Python process: it reads the server Secret into memory, captures
Compose rendering, container inspect, image history, and service logs, exits
nonzero on a byte-for-byte match, and prints neither the key nor the captured
material:

```bash
sudo PHASE2B1_SECRET_FILE=/opt/storylens/shared/secrets/deepseek-api-key \
  python3 - <<'PY'
import os
import pathlib
import subprocess

secret = pathlib.Path(os.environ["PHASE2B1_SECRET_FILE"]).read_bytes()
if not secret:
    raise SystemExit(2)
commands = [
    ["docker", "compose", "--env-file", "online.env", "config"],
    ["docker", "compose", "--env-file", "online.env", "logs", "--no-color"],
]
container_ids = subprocess.run(
    ["docker", "compose", "--env-file", "online.env", "ps", "-aq"],
    check=True,
    stdout=subprocess.PIPE,
).stdout.split()
for container_id in container_ids:
    commands.append(["docker", "inspect", container_id.decode("ascii")])
image_ids = subprocess.run(
    ["docker", "compose", "--env-file", "online.env", "images", "-q"],
    check=True,
    stdout=subprocess.PIPE,
).stdout.split()
for image_id in set(image_ids):
    commands.append(["docker", "image", "history", "--no-trunc", image_id.decode("ascii")])
for command in commands:
    captured = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
    if secret in captured:
        raise SystemExit(1)
PY
```

Do not print, hash, persist, or pass the key through a shell variable during
verification. Logs and public errors must not include API keys, uploaded TXT,
prompts, raw provider bodies, or endpoint credentials.

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
safe to repeat, and never drops or truncates data. On PostgreSQL, initialization
opens one transaction, obtains the fixed StoryLens project
`pg_advisory_xact_lock`, and then uses that same SQLAlchemy connection for both
`metadata.create_all` and the additive Phase 2B1 ledger migration. A concurrent
API or Worker initializer waits for the transaction lock and re-inspects the
committed schema before doing any work. Commit, rollback, or connection loss
automatically releases the lock. SQLite development tests skip the
PostgreSQL-only lock statement. Uvicorn or the worker starts only after the
transaction succeeds; container restart is not part of the migration protocol.

The same check can be run explicitly:

```bash
docker compose --env-file online.env run --rm online-api \
  python -m storylens_online.db.init_schema
```

### PostgreSQL concurrent-initialization acceptance gate

The Hong Kong isolated gate must use two independent database restores. Never
test this by deleting columns from the formal database, and never roll back an
already additive 38-column ledger merely because the application was rolled
back. Preserve row counts and identifiers before and after each run.

For snapshot A, restore an untouched Phase 2A database whose
`online_model_usage_ledger` has 14 columns. Start the API and Worker at the same
time, without relying on a restart policy:

```bash
docker compose --env-file online.env stop online-api online-worker
docker compose --env-file online.env up --no-deps --no-recreate \
  online-api online-worker
docker compose --env-file online.env ps online-api online-worker
if docker compose --env-file online.env logs --no-color online-api online-worker | \
  grep -Eq 'DuplicateColumn|already exists|Traceback'; then
  echo 'Concurrent initialization log gate failed.' >&2
  exit 1
fi
```

Both processes must complete their first initialization successfully. Neither
container may restart, the ledger must have 38 columns, existing uploads, jobs,
and ledger rows must be unchanged, and the only deterministic uniqueness
boundary must remain `(analysis_run_id, attempt_no)`. Record restart counts with
`docker inspect`, and query `information_schema.columns`, `pg_indexes`, and the
preserved row identifiers without printing connection strings or secrets.

For snapshot B, restore a separate Phase 2A database copy and apply only a
strict subset of the Phase 2B1 additive columns using the exact definitions in
the versioned migration. Then repeat the simultaneous API/Worker start. Both
must succeed on their first process lifetime, complete the remaining columns
and constraints once, preserve all rows, and become no-ops when the explicit
initializer command is run again from both roles. A same-named column, index,
or constraint with an incompatible definition must instead fail closed with
the fixed schema-incompatible error; it must not be silently accepted.

These two real-PostgreSQL runs are a deployment gate. SQLite and fake-connection
concurrency tests prove ordering and idempotency contracts but do not replace
the Hong Kong PostgreSQL lock-wait test.

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

### Phase 2B1 private acceptance (do not enable for public users)

After the fake-transport and migration suites pass, the Hong Kong operator must
use an isolated deployment and exactly one internal PocketBase user ID:

1. Keep `phase2a_smoke` as the default and confirm it makes no outbound model
   request and creates no `online_model_usage_ledger` row.
2. Mount the real key file only into `online-worker`, enable the Phase 2B1 gate,
   and place only the internal user ID in the allowlist. Verify the source stays
   `600:0:0`, the tmpfs copy is `400:10001:10001`, the source is unreadable to
   UID 10001, and `/proc/1/status` reports Worker PID 1 as UID 10001.
3. Submit one non-sensitive TXT fixture and confirm every public overview/finding
   cites an input `P000001`-style paragraph ID.
4. Reconcile every Provider attempt's prompt, completion, total, cache-hit and
   cache-miss Token values with the ledger. Confirm hit plus miss equals prompt,
   recalculate the UTC peak/off-peak USD snapshot and frozen USD/CNY conversion,
   then compare the task aggregate; public `charged_cny` and ledger
   `customer_charge_cny` remain 0.
5. Exercise one 429 retry, one usage-complete invalid structured response, and one
   post-send timeout. The first two may use at most two total calls; the timeout
   becomes `unknown` and must not be retried.
6. Restart a worker after an attempt has been durably started. The recovered
   attempt becomes `unknown`, the job stops safely, and no second model call is
   made.
7. Confirm wallet, reservation, transaction, recharge and Afdian records did not
   change. Scan logs for Secret, fixture text, Prompt and raw Provider response
   patterns without printing those values.
8. Inspect every container and image history. Only `online-worker` may reference
   `/run/secrets/storylens_online_deepseek_api_key`; only that service may use
   the staging entrypoint; no image layer, command argument, rendered
   environment, inspect payload, or log may contain the key. Run the in-memory
   real-value scan above and require exit code 0.

Disable the gate and clear the allowlist after the isolated run. Phase 2B1 is not
production-accepted until these real-Provider checks are recorded in its Change
ID; local Fake transport results cannot substitute for them.

This creates missing PostgreSQL tables only. PocketBase owns only its auth
collection migration and is never responsible for StoryLens Online SQL schema.
Future changes to existing columns still require a versioned SQL migration.

`/health/ready` continues to report `afdian_not_configured` when no Afdian
credential is supplied. That is expected in Phase 2A and does not imply that
the no-charge smoke worker uses Afdian.

## Future Hong Kong upgrade procedure

### Lightweight Web/App deployment (CHG-20260903-001)

This is an **operator-initiated** deployment tool, not automatic production
publishing. It has no GitHub Actions, remote Git operations, unattended trigger,
model call, or secret upload. The current local implementation still requires
Hong Kong **isolated** acceptance before production use.

| Classification | Allowed operation |
| --- | --- |
| `web` | Online Web source/tests, `Dockerfile.web`, nginx Web configuration: build/recreate only `online-web` |
| `app` | Explicitly audited ordinary Worker/queue/error files and corresponding tests, Online API `requirements.txt`: build one API image, recreate only API + Worker |
| `full` | Database/model/schema/migration, Compose, API Dockerfile, Worker entrypoint, PocketBase, Caddy, auth/Secret/provider/billing/network/storage boundary, deployment tools, unknown code, or mixed Web + App changes: reject with `FULL_DEPLOYMENT_REQUIRED` |
| `documentation_only` | Online README/roadmap or Change records alone: no deployment |
| `invalid` | Traversal, absolute path, backslash, empty component or malformed path: reject |

The pure classifier lives in `deploy_policy.py`. Case changes cannot bypass the
allowlist. `main.py` currently combines ordinary endpoints with authentication
and upload ownership checks, so it is deliberately **full**, not broadly allowed
as “API code”. The Web `src/api.ts` transport/auth contract also remains full.
Unknown tests/code are not automatically approved. This path gate cannot prove
semantic safety: an auth, cost, storage or schema change hidden inside an allowed
file still requires human review and a full deployment. Adding an allowed path
changes the policy itself and must first pass full acceptance.

#### First installation / trusted baseline

The new scripts are themselves `full`. They must be installed once by the
existing, manually approved full deployment process, not by using this tool to
deploy itself. Preserve all current data/Secret files and the verified 005
baseline. An operator must review and install the same deployment-tool bytes
locally and in `/opt/storylens/current/infra/online`; helpers received in a
bundle are **never executed**. The trusted shell and Python helpers must be
root-owned, not group/world writable, LF-encoded, with the shell executable.
The host needs Python 3.10+ (stdlib only), Docker Compose v2, curl, and sudo.
The SSH account needs operator-approved `sudo -n` access to this root-owned
entrypoint; the script never asks for or passes a sudo password. Do not grant
sudo access to an untrusted/writable script.

Before each command, set `BaselineCommit` to the **full commit currently deployed
for that component**, initially the manually installed full baseline; thereafter
read the non-secret `deployment.json` through `current-web` or `current-app`.
A later commit is allowed only if **all source/build/helper hashes for the target
component are identical to the deployed copy** (for example an already deployed
App-only commit after the last Web commit). This allows alternating components
without reclassifying already deployed changes as pending. Do not blindly use
HEAD's parent or the newest local record commit. The local baseline must be an
ancestor of HEAD. The server independently checks the pointer and every hash,
rejecting source drift before building; any mixed changes still in the chosen
baseline-to-HEAD diff require full deployment.

#### Windows one-command entry

Run in a normal interactive Windows PowerShell terminal from the repository.
Python 3.11/3.12, Git, Windows OpenSSH and (for Web tests) Node/npm must exist.
The script prefers `.venv\Scripts\python.exe`. The host key must already be
verified in `known_hosts`: `StrictHostKeyChecking=yes` is mandatory, not silently
disabled. Replace the placeholders with the actual deployed component commits:

```powershell
$webBaseline = '<full-40-character-deployed-web-commit>'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy_online.ps1 -Mode web -Server ubuntu@43.132.155.132 -IdentityFile "$env:USERPROFILE\.ssh\storylens_hk_ed25519_20260831" -BaselineCommit $webBaseline

$appBaseline = '<full-40-character-deployed-app-commit>'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy_online.ps1 -Mode app -Server ubuntu@43.132.155.132 -IdentityFile "$env:USERPROFILE\.ssh\storylens_hk_ed25519_20260831" -BaselineCommit $appBaseline
```

Append `-DryRun` to check Git cleanliness, version, baseline ancestry and scope
**without tests, packaging, SSH, SCP or any server contact**. It does not prove
remote permissions or health. `-KeepPackage` retains the local temporary source
archive for review; otherwise only the exact task-created temporary directory
is removed. `-SkipTests` is an explicit exceptional bypass with a fixed warning,
never the default. It cannot bypass scope, dirty-tree, integrity or server gates.
`-Domain` defaults to `app.dstorylens.com`.

Default local gates are Web `npm ci`, typecheck, Vitest and production build, or
App full online-backend pytest and compileall. Git is checked again after tests;
the package must still use the same HEAD. No uncommitted/ignored runtime data is
included. Source is read through `git archive` and combined only with a generated
non-secret manifest (commit, baseline, changed paths, source SHA256 and protocol).
The compressed package gets a second SHA256 check by PowerShell before SCP and
again by the server. Files are uploaded under a unique
`/tmp/storylens-deploy-<random-id>.tar.gz` name; all remote-shell tokens are
strictly validated and quoted. Native output is captured, not echoed; errors
and the final result are fixed codes, never raw stack traces or credentials.

An encrypted SSH key may ask for its passphrase separately for SCP and SSH if
it is not already loaded. Use the Windows `ssh-agent` service and `ssh-add` in
your interactive terminal to unlock it once; **never remove the private-key
passphrase**, store it in this script, pass it as an argument, or paste the key.
The tool checks only the private-key **path**, not its contents. Host-key and
agent setup remain explicit operator actions, not automated by this script.

#### Build contexts and immutable component releases

Both Dockerfiles use repository-relative `COPY` paths. Therefore each minimal
archive keeps the original directory layout with a small root build context:

- Web: `apps/online_web/**`, `Dockerfile.web`, `nginx-online.conf`;
- App: `apps/online_api/**` (including its own requirements/tests),
  `Dockerfile.api`, unchanged `worker-entrypoint.sh`;
- both: `VERSION`, `deployment.json`, trusted shell, runtime, package and policy
  helper sources for audit/hash checking. No whole repository copy.

There is no `.env`, `online.env`, Secret, dump, uploaded TXT, PocketBase data,
node_modules or local build output in either archive. Members are allowlisted,
literal secret patterns scanned, bounded to 128 MiB expanded / 5,000 files,
and links/special files/duplicate case-folded paths rejected. Extraction creates
regular files exclusively in a new `/opt/storylens/releases/<full-commit>`.
An existing directory is never overwritten; even a failed build's directory is
retained. Reattempt with a newly reviewed commit, not by quietly deleting history.

#### Pointer, Compose and data safety

**`/opt/storylens/current` never changes during a lightweight deployment.** It
continues to point to the complete, manually accepted infrastructure release.
Moving it to a Web-only archive would lose the other Dockerfiles/Compose/config,
so success instead atomically switches `current-web` or `current-app`.

Production continues to use project `storylens-online`, the stable base Compose
and `/opt/storylens/shared/online.env`. A generated root-only, non-secret
`/opt/storylens/shared/lightweight-compose.json` contains only component image
tags and, for App, explicit non-migration startup commands. It preserves the
other component's settings. All later Compose operations **must include this
override** until an operator reconciles it in the next full deployment:

```bash
sudo docker compose --project-name storylens-online \
  --project-directory /opt/storylens/current/infra/online \
  --env-file /opt/storylens/shared/online.env \
  -f /opt/storylens/current/infra/online/docker-compose.yml \
  -f /opt/storylens/shared/lightweight-compose.json ps
```

Do not use an old naked `compose up` or `compose build` after a component update:
it can select the old Web image or reintroduce the full-start migration command.
For a later full release, first reconcile both component commit pointers/images,
take backups, inspect the override, and explicitly adopt the complete source and
startup policy. Do not move global `current` to a partial archive or discard an
active override as routine cleanup.

The tool obtains a host-side exclusive `flock` for the entire operation. It
builds a commit-tagged image, captures actual old image IDs, keeps deterministic
`storylens-online-<mode>:rollback-<full-commit>` tags, maps the candidate to the
live component tag, and runs only `up -d --no-build --no-deps` for its targets.
Web never starts an init service or mounts/reads a Secret. App starts Uvicorn
directly and the Worker module directly (retaining the unchanged gosu/Secret
entrypoint), **without `init_schema` or migration**. Even App rollback uses
these no-migration commands. API/Worker must share the same old image ID.

It waits for Web/API health and Worker running with restart count zero, then
checks HTTPS root 200 against the **local gateway** using curl `--resolve` and
TLS verification. It compares every non-target container ID (including gateway
and exited pocketbase-init) before/after. All six existing named volumes must
exist beforehand and retain their creation identity; the tool never issues
volume create/remove commands or Compose down. No ports, network, database,
PocketBase migration, user file, credential or feature flag is modified.

#### Failure and rollback

Health, restart, unrelated-container/volume drift or pointer-switch failure
restores the old live image tag and recreates only the same target service(s),
rechecks health and keeps component/global pointers at their old values.
`DEPLOY_FAILED_ROLLED_BACK` is still a nonzero result. Existing release folders,
rollback tags and the uploaded source package remain available for audit.

If rollback itself fails, or the host/process is killed before cleanup, a
non-secret `lightweight-pending.json` blocks later deploys with
`MANUAL_RECOVERY_REQUIRED`. Do not repeatedly rerun or delete this marker to
force progress. An operator must inspect its mode/commit/rollback tag, restore
that tag to the live image name, run the same targeted no-build/no-deps Compose
operation with the override, check health/container/volume identities and
component pointers, and only then clear that specific pending marker. The
script does not claim atomicity across Docker containers and filesystem state
during power loss. Full rollback images, backups and the global infrastructure
baseline are never deleted by this tool.

#### Remaining Hong Kong isolated acceptance (not yet executed)

Use isolated data and non-production infrastructure in a disposable host/VM
with the production-shaped paths/project; do **not** run fault injection against
the formal `storylens-online` stack. The production entrypoint has intentionally
fixed paths/project and no test-environment override arguments.

1. Manually install the trusted tool baseline, verify root ownership/executable
   LF shell, SSH host key, agent/passphrase flow and limited sudo access.
2. Deploy one harmless Web-only commit; confirm only Web container ID changes,
   root 200, no init/Secret access, current unchanged, current-web switched.
3. Deploy one ordinary Worker/queue commit; confirm only API/Worker IDs change,
   no database initialization/DDL, old uploads/jobs/ledger remain intact,
   Secret wrapper still drops to UID/GID 10001 and disabled gate stages nothing.
4. Reconcile manifests, images, source hashes, all six volume identities and
   shared override across alternating Web/App deployments.
5. Induce failing health and pointer write in isolation; verify automatic old
   image recovery, rollback failure marker, and explicit manual recovery.
6. Check wrong baseline, dirty Git, mixed/full paths, SHA mismatch, duplicate
   release and malformed archive are rejected. Scan logs/Compose/inspect/image
   history for actual secret values **locally on the host**, never print them.

Local Fake Docker/curl and PowerShell Fake SSH/SCP tests are not evidence of
these Linux Docker/SSH/network gates. No Hong Kong operation has been performed
as part of implementing this mechanism.

### Manual full upgrade

Do these steps only during an approved deployment window, reconciling any
lightweight component pointers/override as described above:

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

Do not run `docker compose down -v`, delete volumes, or manually remove Online
tables as a rollback shortcut.

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
- Phase 2B1 is an internal real-model gate, not a public paid Beta: whole-book
  analysis, wallet billing, Afdian recharge, and public onboarding remain out of
  scope.
