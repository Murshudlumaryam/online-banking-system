# End-to-end tests (Playwright)

Real browser-driven tests against the real frontend + real backend + real
PostgreSQL/Redis — no mocking. `helpers.ts` uses the API directly for fast
fixture setup (registering users, creating accounts), then each spec drives
the actual UI for the behavior under test.

## The OTP problem, and how these tests solve it

A real customer confirms a transfer with a code sent by SMS/email. An
automated browser has no inbox to read. The app deliberately never logs or
returns the real OTP through any normal channel (see `README.md`'s security
notes) — so these tests use three narrowly-scoped, **test-environment-only**
endpoints that a real production deployment can never expose:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/transactions/{id}/debug-otp` | Reads (read-once) the OTP just generated for a transaction |
| `POST /api/v1/auth/debug-promote-to-admin` | Promotes the current user to ADMIN (registration only ever creates CUSTOMER) |
| `POST /api/v1/admin/accounts/{id}/debug-set-balance` | Seeds a starting balance (there's no real "deposit" feature — money only moves between two of this system's own accounts) |

All three call `app.core.test_mode.is_test_environment()` and return a plain
404 — indistinguishable from "doesn't exist" — unless the backend is running
with `ENVIRONMENT=test`. They are also excluded from the OpenAPI schema
(`include_in_schema=False`), so the generated TypeScript client never sees
them either. See `backend/app/core/test_mode.py` and the `debug-*` routes
for the full implementation.

## Running locally

```bash
# Terminal 1 — backend, pointed at a disposable database, in test mode
cd backend
export DATABASE_URL=postgresql+asyncpg://banking_user:banking_pass@localhost:5432/banking_e2e_db
export REDIS_URL=redis://localhost:6379/0
export JWT_SECRET_KEY=e2e-local-secret
export RATE_LIMIT_BACKEND=memory
export ENVIRONMENT=test
alembic upgrade head
uvicorn app.main:app --port 8000

# Terminal 2 — frontend + Playwright (Playwright starts the dev server itself)
cd frontend
npx playwright install chromium   # first time only
npm run test:e2e
```

Use a **disposable, dedicated database** for this (not the one your `pytest`
suite targets) — the pytest suite's schema fixture drops and recreates
tables independently of Alembic's migration history, and running both
against the same database in the same session will make one clobber the
other's schema.

## Known limitation in this sandbox

Playwright's browser binaries are downloaded from `cdn.playwright.dev`,
which is outside this project's network egress allowlist here, and the
Ubuntu `chromium` package on this base image is a snap stub with no working
snap daemon — so **no real browser could be launched in this development
sandbox**, and these specs could not be executed here.

What *was* verified here instead, directly against the real running
backend (Postgres + Redis, `ENVIRONMENT=test`):
- Every API call these specs make (register → login → promote-to-admin →
  create accounts → seed balance → initiate transfer → read debug OTP →
  confirm → verify balances) was replayed manually end-to-end and produces
  the exact expected result.
- `tsc -p tsconfig.e2e.json --noEmit` — the spec files type-check cleanly
  against `@playwright/test`'s real types.
- Every selector in these specs (`getByLabel`, `getByRole`, etc.) was
  cross-checked by hand against the actual rendered component source
  (`TransferPage.tsx`, `OtpConfirmModal.tsx`, `AdminCustomersPage.tsx`, ...).

That manual API-level replay caught one real bug along the way: the
`debug-promote-to-admin` endpoint's first draft was missing an explicit
`session.commit()` after `UserRepository.save()` (which only flushes) — the
role change was silently rolled back once the request's session closed.
It's fixed now and covered by a backend regression test
(`test_debug_promote_to_admin_actually_persists_across_real_separate_connections`
in `backend/tests/modules/core/test_test_otp_store.py`) using two genuinely
independent database connections, specifically because the ordinary pytest
fixture setup (which shares one connection per test) couldn't have caught
it.

`.github/workflows/ci.yml` installs real Playwright browsers on the GitHub
Actions runner (which has normal internet access) and runs this whole suite
for real on every push — see the `e2e` job.
