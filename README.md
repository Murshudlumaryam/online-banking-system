# Online Banking System

Enterprise-grade closed-loop online banking platform — FastAPI + PostgreSQL +
Redis + Celery backend, React + TypeScript frontend, fully containerized,
production-hardened, and independently audited.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.x (async), PostgreSQL 16,
  Redis, Celery, Argon2, JWT, TOTP 2FA (encrypted at rest), Prometheus metrics
- **Frontend**: React 18, TypeScript, Vite, TailwindCSS, React Query,
  an OpenAPI-generated typed API client, Playwright e2e specs
- **Ops**: Docker Compose (dev + hardened prod with Caddy/HTTPS), GitHub
  Actions CI/CD, Alembic migrations

## Quick start (local development)

```bash
cp .env.example .env      # set a real JWT_SECRET_KEY
docker compose up --build
docker compose exec backend alembic upgrade head
```

Backend: http://localhost:8000/docs · Frontend: http://localhost:5173

## Documentation

| Doc | Covers |
|---|---|
| [`backend/README.md`](backend/README.md) | Full build history phase-by-phase, every bug found and fixed (with root cause), test coverage, security notes |
| [`frontend/README.md`](frontend/README.md) | Design system, auth flow, OpenAPI client generation, known limitations |
| [`frontend/e2e/README.md`](frontend/e2e/README.md) | Playwright e2e setup and the test-only debug endpoints they rely on |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Step-by-step cloud VM deployment (AWS/DigitalOcean/GCP), zero-downtime migration strategy, observability |

## Feature highlights

Registration/login, JWT access + rotating refresh tokens, optional TOTP 2FA
(secret encrypted at rest with Fernet), accounts, cards, OTP-confirmed money
transfers with double-entry ledger accounting, scheduled/recurring payments,
beneficiaries, PDF statements, admin back office, full audit logging, real
email (SMTP) and SMS (Twilio) notification providers with delivery metrics,
Prometheus `/metrics` (multiprocess-safe under gunicorn), rate limiting,
and a production startup guard that refuses to boot with insecure config
(weak JWT secret, wildcard CORS, missing encryption key).

## Verified, not assumed

This project has been through multiple rounds of real verification, not just
code review — including two genuine concurrency bugs found and fixed via
tests that race real, independent database connections against each other
(not mocked), and dependency vulnerabilities found and patched via
`pip-audit`/`npm audit`. See `backend/README.md`'s phase-by-phase notes for
the full account of what was tested, how, and what's explicitly still
unverified (e.g. this project has never been run through a live Docker
daemon or a real cloud deployment — see the "known limitations" sections
throughout for a complete, honest list).
