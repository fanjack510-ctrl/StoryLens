# StoryLens Online — Hong Kong beta foundation

This stack is independent from the packaged StoryLens 1.3.6 desktop runtime.
It currently starts the online API foundation, PocketBase, PostgreSQL, Redis and
the HTTPS gateway. It does **not** yet expose the existing desktop analysis
routes or a production online frontend.

## Server prerequisites

- Hong Kong x86_64 Linux host (Ubuntu 22.04 LTS recommended)
- Docker Engine and Docker Compose v2
- A domain A record pointing to the host
- inbound TCP 80/443; database and PocketBase ports remain private

## Configure

```bash
cd infra/online
cp .env.example .env
chmod 600 .env
```

Replace every placeholder in `.env`. Secrets stay on the server only. The
desktop application's provider credentials and offline licence data are not
read or copied by this stack.

## Start the foundation

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl https://YOUR_DOMAIN/health/live
curl https://YOUR_DOMAIN/health/ready
```

After PostgreSQL reports healthy, the `online-api` container runs
`python -m storylens_online.db.init_schema` before starting Uvicorn. The
initializer creates the five missing `online_` tables with SQLAlchemy
`metadata.create_all`, is safe to run repeatedly, and never drops or truncates
existing data. If schema initialization fails, Uvicorn is not started and the
container exits so the failure remains visible to Docker instead of serving an
API against an empty database.

The same idempotent initialization can be rerun explicitly when diagnosing a
deployment:

```bash
docker compose run --rm online-api python -m storylens_online.db.init_schema
```

This bootstrap step owns only the StoryLens Online PostgreSQL tables. It is not
a PocketBase migration and does not change the Redis, PocketBase or Caddy
boundaries. Future destructive or structural schema changes still require a
versioned migration mechanism; this initializer only creates currently missing
tables.

Create the first PocketBase superuser from the server terminal; never expose
the PocketBase port publicly:

```bash
docker compose exec pocketbase /pb/pocketbase superuser create ADMIN_EMAIL STRONG_PASSWORD
```

`/health/ready` remains `configuration_pending` until Afdian credentials are
provided. That is intentional while the recharge product is not yet created.

## Security boundaries

- Do not publish `.env`, database dumps or PocketBase `pb_data`.
- Do not open ports 5432, 6379, 8090 or 8080 in the cloud firewall.
- Back up PostgreSQL and PocketBase to storage outside this server.
- The Afdian token is server-only and is never returned by a health endpoint.
- Billing money fields use decimal storage; external order numbers and ledger
  idempotency keys are unique.
