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
does not hide migrations packaged in a newer image. PocketBase applies pending
migrations when `serve` starts.

## Server prerequisites

- Hong Kong x86_64 Linux host (Ubuntu 22.04 LTS recommended)
- Docker Engine and Docker Compose v2
- a domain A/AAAA record pointing to the host
- inbound TCP 80/443 only

## Configure

```bash
cd infra/online
cp .env.example .env
chmod 600 .env
```

Replace every placeholder in `.env`. Secrets stay on the server only. The
desktop provider configuration, local database, licence data, and API keys are
not read or copied by this stack. `UPLOAD_MAX_BYTES` is non-secret and defaults
to 10485760 (10 MiB).

Worker Redis timing is also non-secret. The defaults are a 5-second blocking
poll, a 15-second socket read timeout, a 5-second connect timeout, and bounded
retry delays from 1 to 15 seconds. Startup validation requires the socket read
timeout to exceed the blocking poll by at least 2 seconds and requires the
maximum retry delay to be no smaller than the initial delay. Invalid timing
combinations stop the worker before it connects and never print the Redis URL.

## Validate and start

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
curl https://YOUR_DOMAIN/health/live
curl https://YOUR_DOMAIN/health/ready
```

After PostgreSQL is healthy, both application roles first run
`python -m storylens_online.db.init_schema`. The initializer creates all seven
currently registered `online_` tables with SQLAlchemy `metadata.create_all`, is
safe to repeat, and never drops or truncates data. Uvicorn or the worker starts
only after initialization succeeds.

The same check can be run explicitly:

```bash
docker compose run --rm online-api python -m storylens_online.db.init_schema
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
2. Fetch and check out the approved commit without changing the server `.env`.
3. Run `docker compose config --quiet` and `docker compose build`.
4. Run `docker compose up -d`; do not add `-v`, because named volumes must be
   preserved.
5. Confirm container health, both health endpoints, registration/login,
   one non-sensitive TXT smoke task, and that only 80/443 are public.

## Rollback procedure

1. Preserve logs and take another database/upload snapshot before rollback.
2. Check out the previously recorded approved commit.
3. Rebuild and run `docker compose up -d` without deleting named volumes.
4. Verify health and login. If the older application cannot read an additive
   schema change, stop application traffic and restore the matching pre-upgrade
   backups as a coordinated data rollback.

Do not run `docker compose down -v`, delete volumes, or manually remove the two
Phase 2A tables as a rollback shortcut.

## Security and operating boundaries

- Never commit `.env`, database dumps, PocketBase data, upload contents, or
  tokens.
- Do not publish ports 5432, 6379, 8090, or either internal 8080 service.
- Uploaded content and original text are not logged. Public errors contain
  stable codes rather than exception stacks or internal connection details.
- Uploads accept non-empty UTF-8/UTF-8-SIG `.txt` only, use server-generated
  storage keys, enforce the configured size limit, and persist SHA-256.
- Every upload, job, and result query is scoped to the authenticated PocketBase
  user ID to prevent cross-user access.
- Phase 2A is not the formal public Beta: real whole-book analysis, model APIs,
  x2 billing, Afdian recharge, and public onboarding remain out of scope.
