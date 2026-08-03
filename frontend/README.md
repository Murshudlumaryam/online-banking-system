# Online Banking System â€” Frontend (Phase 5)

React + TypeScript + Vite + a small internal SPA router + React Query + Axios + TailwindCSS,
implementing the full customer and admin UI sitemap from the architecture
blueprint.

## Design system

A distinct "ledger" identity rather than generic SaaS defaults:

- **Color**: deep ledger-navy (`ledger-700` `#123C4D`) as the primary action
  color, a brass accent (`brass-500` `#B8935F`) reserved for currency/coin
  associations, forest green / brick red / amber for success/danger/warning,
  on a warm paper background (`#F7F6F2`) â€” evokes a physical ledger book
  rather than a generic dashboard.
- **Type**: Source Serif 4 for headings (authority, letterhead feel), Inter
  for UI text, **IBM Plex Mono with tabular figures** for every monetary
  amount and account/card number â€” so columns of numbers actually align,
  the way a real ledger or bank statement does.
- **Signature element**: "the ledger line" â€” every transaction's debit/credit
  entries render with a colored dot (brick=debit, forest=credit), a hairline
  divider, and tabular-mono amounts with explicit +/- signs, instead of
  generic card shadows. See `TransactionDetailPage` / `AdminTransactionDetailPage`.

## What was built

- **Project setup**: Vite + React 18 + TypeScript (strict mode) + TailwindCSS
  with the custom token system above; Vitest + React Testing Library for tests
- **API layer** (`lib/apiClient.ts`): axios instance that attaches the bearer
  token to every request and **automatically rotates the refresh token on a
  401** â€” concurrent requests that all 401 at once share a single in-flight
  refresh instead of racing (which would trip the backend's reuse-detection
  and log everyone out). `services/*.ts` wrap every backend endpoint with
  typed request/response contracts mirrored from the backend Pydantic schemas.
- **Auth** (`context/AuthContext.tsx`): login/register/logout, session
  persisted via refresh token, role read from the (client-side-only-trusted)
  JWT claims for navigation â€” the backend independently re-validates every
  request regardless of what the frontend believes about the role.
- **Customer pages**: Dashboard, Accounts (list/detail), Transfer (with OTP
  confirmation modal + countdown, beneficiary autocomplete via `<datalist>`,
  and explicit terminal-vs-retryable OTP error handling), Transactions
  (list/detail with the ledger-line rendering), Beneficiaries (full CRUD),
  Cards (rendered as ID-1 aspect-ratio card faces), Profile (+ change password)
- **Admin pages**: Customers (list/detail/block/reactivate/open account),
  Accounts (list/filter/status change/issue card), Transactions
  (monitor/detail), Exchange rates (list/create), Audit logs (filterable
  search)
- **React Query** for all server state â€” no manual loading/error state
  duplication, automatic cache invalidation after mutations (e.g. confirming
  a transfer invalidates accounts + transactions + dashboard in one place)

## Auth token storage

Tokens are delivered through backend-set HttpOnly cookies. The frontend does not store access or refresh tokens in `localStorage`; session bootstrap uses `GET /api/v1/auth/session` and all API clients send `credentials: "include"`.

## Running it

```bash
cp .env.example .env   # points at the backend's /api/v1
npm install
npm run dev             # http://localhost:5173
```

Or via Docker Compose from the project root (`docker compose up --build`) â€”
the `frontend` service is already wired to the `backend` service.

## Testing

```bash
npm run build   # tsc -b (strict typecheck) && vite build â€” both verified clean
npx vitest run  # 28/28 passing: format helpers, JWT decode/expiry, token
                 # storage, Button, OTP modal (digit-only input, 6-digit
                 # gate, error display, cancel), LoginPage (validation,
                 # error display, calls the real service contract)
```

`npm run build` and `npx vitest run` were both executed against this exact
codebase â€” not just written and assumed to work. One real bug was found and
fixed during that verification (see below).

### Bug found and fixed during verification
`formatMoney`'s fallback path (for a malformed currency code) was originally
tested against `"XXX"` â€” which is actually a valid ISO 4217 code (means "no
currency") that `Intl.NumberFormat` accepts without throwing, so it never
reached the catch branch the test meant to exercise. Fixed the test to use a
genuinely malformed code (`"AB"`, wrong length) â€” confirmed the fallback
branch is reachable and correct.

## OpenAPI-generated client (Phase 8)

`src/api/generated/schema.d.ts` is generated straight from the backend's
real OpenAPI schema (`npm run generate:api` â€” runs
`backend/scripts/export_openapi.py`, which calls `app.openapi()` directly,
no running server or DB needed â€” then `openapi-typescript`). `src/api/client.ts`
wraps it with `openapi-fetch`, with the same JWT-attach + refresh-on-401
middleware as the hand-written axios client. **Every** `services/*.ts` file
now calls through this generated, fully-typed client â€” if the backend
changes a field name or a route disappears, `npm run build` fails at the
exact call site instead of failing silently at runtime.

Two HTTP clients coexist deliberately: `lib/apiClient.ts` (axios, from Phase
5) is still used by `AuthContext`'s bootstrap-refresh call, since splitting
that one call out wasn't worth the churn; everything else goes through the
generated client. `getApiErrorMessage`/`getApiErrorCode` in `lib/apiClient.ts`
handle both clients' error shapes uniformly.

## End-to-end tests (Playwright, Phase 8)

Real browser, real backend, real PostgreSQL/Redis â€” `e2e/auth.spec.ts`,
`e2e/transfer.spec.ts` (full transfer including real OTP confirmation),
`e2e/admin.spec.ts`. See **`e2e/README.md`** for the full write-up,
including three narrowly-scoped, `ENVIRONMENT=test`-only backend endpoints
these specs need (there's no other way for an automated browser to read an
OTP that's deliberately never logged anywhere).

## Known limitation

Playwright's browser binaries download from `cdn.playwright.dev`, which is
outside this sandbox's network egress allowlist, and the OS's `chromium`
package here is a snap stub with no working snap daemon â€” **no browser
could actually be launched in this development sandbox**, so these specs,
while written and type-checked, could not be executed here directly.

To compensate, every API call the specs make was manually replayed
end-to-end against the real running backend (see `e2e/README.md` for the
full account) â€” which is exactly how a real bug was found and fixed (a
missing `session.commit()` in one of the test-only debug endpoints).
`.github/workflows/ci.yml`'s `e2e-tests` job installs real browsers on the
GitHub Actions runner (normal internet access) and runs the full suite for
real on every push.

## Dependency audit

`react-router-dom` was removed in Phase 10 and replaced with `src/lib/router.tsx`, a small internal SPA router adapter. Vite/Vitest were upgraded to audited safe versions. `npm audit` reports 0 vulnerabilities.

## Next step

All planned phases through Phase 10 are complete. Remaining external checks require a working Docker daemon: production image build/run and Playwright e2e against the composed stack.

## Phase 10 auth/dependency update

The frontend no longer stores access or refresh tokens in `localStorage`. Auth is cookie-based: backend login/MFA/refresh responses set HttpOnly cookies and the app restores state with `GET /api/v1/auth/session`. The old `lib/tokenStorage.ts` helper was removed.

React Router was replaced with a small internal SPA router adapter (`src/lib/router.tsx`) to remove the audited vulnerable runtime dependency while preserving the app's existing `Link`, `NavLink`, `Navigate`, `Outlet`, and route-config usage. `npm audit` now reports 0 vulnerabilities.

Verified: `npm run build`, `npm run lint`, `npm test -- --run`, and `npm audit`.

