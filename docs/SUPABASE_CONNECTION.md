# Supabase connection

Project: `qjcudbkamhldswcyxypv`, URL `https://qjcudbkamhldswcyxypv.supabase.co`.

The React/Vite frontend and FastAPI token verifier now use this project instead of the previous one. Installed and pinned `@supabase/supabase-js`2.119.0 and `@supabase/ssr`0.12.7; the npm lockfile is updated. Installed the official `supabase` and `supabase-postgres-best-practices` agent skills into the user's Codex skills directory. Those skills are available on the next turn.

## Actual state

- Backend `.env`: updated `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` only; unrelated settings preserved.
- Frontend `.env` and `.env.local`: updated `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`. The latter also contains the supplied `NEXT_PUBLIC_` aliases; Vite uses the `VITE_` values.
- Browser sessions persist and refresh through the existing Supabase singleton and `AuthContext` listener. Storage is scoped to the project hostname, so tokens from the old project are not reused. This is a Vite SPA, so Next.js `next/headers` server components/middleware are not part of its runtime. The installed SSR package is available if SSR is introduced later.
- Live Auth health/settings return200; email sign-in is enabled and email confirmation is required. The backend retrieved one real ES256 public signing key from the configured project. Tokens require its exact issuer and audience.
- Signup confirmation and password-reset redirects target the current app's `/login`. In Supabase Authentication → URL Configuration, set Site URL to `http://localhost:5173` and allow `http://localhost:5173/login` (plus the actual production origin when deployed). These dashboard settings cannot be changed using a publishable key and have not been modified here.
- Actual Chromium check: anonymous protected navigation redirects to login; the live browser SDK targets this hostname, reads its Auth settings successfully, reports no session errors and returns no customer records. Responses were not mocked. Signed-in account testing is unrun because a confirmed account/password was not supplied.
- The browser's zero-row `profiles` probe returns404/PGRST205. Hosted UI tables are not available through the Data API yet. The publishable key does not authorize creating those tables, buckets or migrating PostgreSQL.
- **Analytics database migration is pending `SUPABASE_DATABASE_URL`.** The existing local database and storage volumes remain active. No hosted schema/data mutation or runtime-role creation has been performed.

## Credential needed to finish the requested database move

In the project's Supabase dashboard, open **Connect → Session pooler**. Copy the PostgreSQL URI with the actual database password, and put it in the backend's root `.env`:

```dotenv
# Server-only; never add this to frontend/.env or a VITE_/NEXT_PUBLIC_ variable.
SUPABASE_DATABASE_URL=postgresql://postgres.qjcudbkamhldswcyxypv:YOUR_URL_ENCODED_DATABASE_PASSWORD@YOUR_SESSION_POOLER_HOST:5432/postgres
DATABASE_TARGET=local
```

The `https://...supabase.co` API URL and `sb_publishable_...` key are different credentials and cannot replace this URI. Copy the actual region/host from Connect rather than guessing. Direct connections are also supported; the Session pooler avoids IPv6-only connectivity problems in environments without IPv6. Transaction pooling on6543 is rejected because this app depends on session schema selection. See [Supabase PostgreSQL connections](https://supabase.com/docs/guides/database/connecting-to-postgres).

## Prepared migration and cutover

`scripts/migrate_to_supabase.py` defaults to read-only preflight. It validates the database host/username against the configured project, normalizes psycopg/TLS, requires current source migrations and checks for conflicting/nonempty target tables before any changes. The hosted application schema is **`analyst`**, separate from the public Supabase UI schema. API, standalone worker, monitoring and Alembic use the same schema binding. Public Supabase tables are never used as fallback analytics tables.

The migration uses all ORM tables **plus** the three separately declared authorization membership/binding tables. It copies via PostgreSQL COPY in one target transaction, verifies row counts and SHA256 of ordered CSV streams, preserves SQL NULL versus JSON null, precision, timestamps and immutable evidence, and resets sequences. It refuses existing target data and keeps the source database. Supabase `auth`, `storage` and system schemas are not copied from the local application database.

For a fresh project, `--initialize-ui` runs the repository's existing hosted UI/Storage schema and explicit owner-protected grants. It refuses existing public application tables instead of changing their semantics. The manual destructive rollback script was moved to `supabase/rollback/`; it is no longer in the forward migration directory. Existing application tables require schema inspection rather than blind initialization.

After copying, the tool creates a scoped login with `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`, grants access only to the private application schema, and saves its generated URI to the private env file. It verifies that this runtime login can inspect the expected schema. `SUPABASE_DATABASE_URL` remains the migration-owner connection; runtime mode requires the separate generated `SUPABASE_RUNTIME_DATABASE_URL`. Nothing automatically switches a live server during copying.

Once the real connection is configured, these commands perform the explicit local-to-hosted move. Run from the repository root, with a database backup, and keep every API/standalone worker stopped until the copy is verified:

```powershell
# Read-only preflight with the newly edited env file:
docker compose run --rm --no-deps backend python scripts/migrate_to_supabase.py

# Take a pg_dump backup first, as done before the local migration startup.
docker compose stop backend
# Also stop any separately launched python -m backend.jobs.job_worker process.
docker compose run --rm --no-deps -v 'C:\data analyst\.env:/run/analyst.env' backend python scripts/migrate_to_supabase.py --apply --source-stopped --initialize-ui --runtime-env-file /run/analyst.env
```

Only after `copy_verified` and runtime validation, change `DATABASE_TARGET=supabase` in root `.env` and recreate the backend:

```powershell
docker compose up -d --force-recreate backend
Invoke-RestMethod http://localhost:8000/health/ready
```

Rollback of the connection is `DATABASE_TARGET=local`, followed by recreating the backend. Keep the original database and storage volumes. Once users write to the hosted database, returning to the old local snapshot does not synchronize those new writes; plan reconciliation before a later rollback.

Uploaded files and Chroma indexes stay on the current server's volumes. New authenticated uploads can use the hosted private `user-datasets` bucket after its initialization. Existing files are not silently uploaded under other users' identities. Local password accounts are not imported into Supabase Auth or linked by matching email; their UUIDs and ownership records are preserved. A verified account/workspace migration requires explicit identity mapping rather than granting an unrelated hosted account access to old data.

No Supabase CLI project link or hosted `db push` has been performed with a publishable key. Current CLI3 defaults database commands to local targets; hosted changes require explicit remote targeting. Consult `supabase --help` for the installed version before using the dashboard's CLI example. This application's private schema uses its existing Alembic chain rather than mixing its tables with the differently shaped public UI migration.

## Verification

`backend/tests/test_supabase_connection.py` covers connection/password/project/pooler guards, signed issuer/audience rejection, complete private-schema migration, exact data copying, refusal of nonempty targets, restricted runtime roles, and full application copying followed by real workspace authorization and immutable decision checks. The regression includes existing schema, dataset isolation and verified-supervisor integration checks. All database writes for these tests use the separate `analyst-supabase-verify` Compose project and synthetic data.

```powershell
docker compose -p analyst-supabase-verify -f docker-compose.verify.yml run --rm runner python scripts/run_setup_tests.py backend/tests/test_supabase_connection.py backend/tests/test_verified_learning_integration.py tests/test_schema_contract.py tests/test_authenticated_dataset_isolation.py
```

Observed final test result:39 passed. Production TypeScript/Vite build, targeted ESLint and Ruff passed. `docs/supabase-verification/browser.json` records the actual read-only browser result. Remote schema migrations, hosted row/storage policies, hosted runtime role access and a signed-in user journey remain unverified until the required database/account credentials are supplied.
