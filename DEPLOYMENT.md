# Deploying to a Cloud VM (AWS / DigitalOcean / GCP)

This guide gets the full stack running on a single Linux VM, reachable over
real HTTPS at your own domain, using the `docker-compose.prod.yml` /
`Dockerfile.prod` / `Caddyfile` in this project. It's written to be generic
across providers — the only provider-specific parts are provisioning the VM
itself (step 1) and opening firewall ports (step 2), both called out below.

**What you need before starting:** a cloud account (AWS/DigitalOcean/GCP), a
domain name you control, and about 20 minutes.

---

## 1. Provision the VM

Any of these give you the same thing: a public IPv4 address and SSH access.

- **DigitalOcean** (simplest): Create a Droplet → Ubuntu 24.04 LTS → at
  least the 2 GB RAM / 1 vCPU plan (2 vCPU / 4 GB recommended for
  comfortable headroom under load) → add your SSH key → create.
- **AWS EC2**: Launch an instance → AMI: Ubuntu Server 24.04 LTS →
  instance type `t3.small` (2 GB) or `t3.medium` (4 GB) → create/select a
  key pair → in the Security Group, allow inbound TCP 22, 80, 443 from
  anywhere (0.0.0.0/0) → launch.
- **GCP Compute Engine**: Create instance → Ubuntu 24.04 LTS → `e2-small`
  or `e2-medium` → under Firewall, check "Allow HTTP traffic" and "Allow
  HTTPS traffic" → create. Add your SSH key via the metadata section or use
  `gcloud compute ssh`.

Note the VM's **public IPv4 address** — you'll point DNS at it next.

## 2. Point your domain at the VM

In your domain registrar / DNS provider, add an **A record**:

```
Type: A
Name: bank            (or @ for the root domain)
Value: <the VM's public IPv4 address>
TTL: 300 (5 min)
```

Wait for it to propagate (`dig bank.example.com` should return the VM's IP —
usually a few minutes, occasionally up to an hour). **Caddy needs this to
already be correct before it starts**, or the automatic HTTPS certificate
request will fail.

If your cloud provider's firewall/security group doesn't already allow it
(AWS/GCP steps above did), make sure inbound TCP **80** and **443** are open
to `0.0.0.0/0` — Caddy needs 80 for the Let's Encrypt HTTP-01 challenge and
443 for HTTPS itself. Port 22 (SSH) should be open too, ideally restricted
to your own IP if your provider supports it.

## 3. SSH in and install Docker

```bash
ssh ubuntu@<VM_IP>          # user is "ubuntu" on DigitalOcean/AWS Ubuntu
                             # images; "root" on some providers

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker                # or log out and back in

docker --version              # sanity check
docker compose version
```

## 4. Get the project onto the VM

Either `git clone` your repository, or upload the project archive directly:

```bash
# From your own machine, if you're uploading the zip instead of using git:
scp online-banking-COMPLETE.zip ubuntu@<VM_IP>:~/
ssh ubuntu@<VM_IP>
unzip online-banking-COMPLETE.zip -d online-banking && cd online-banking
```

## 5. Configure secrets

```bash
cp .env.production.example .env
nano .env    # or vim/your editor of choice
```

Fill in at minimum:
- `DOMAIN_NAME` — the real domain from step 2 (e.g. `bank.example.com`)
- `POSTGRES_PASSWORD` — generate with `openssl rand -base64 32`
- `JWT_SECRET_KEY` — generate with `openssl rand -base64 32`
- `ENCRYPTION_KEY` — generate with:
  `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  (needs a machine with Python + `cryptography` installed — your own laptop
  is fine, this doesn't need to run on the VM). The app **refuses to start**
  in production without a valid one — see "Production configuration guard"
  below. Back this key up as carefully as the database itself: losing it
  permanently locks out every customer who enrolled in 2FA, since their
  stored TOTP secret becomes undecryptable.

Leave `EMAIL_BACKEND=console` and `SMS_BACKEND=console` until you have real
SMTP/Twilio credentials — the app works fully without them, it just logs
OTP/notification content instead of sending it (see `backend/README.md`'s
Phase 7/8 notes). Fill in the `SMTP_*`/`TWILIO_*` values and flip the
backend to `smtp`/`twilio` whenever you're ready for real delivery. Once
you do, `notification_delivery_total{channel,outcome}` in `/metrics` (see
step 11) tells you whether deliveries are actually succeeding.

```bash
chmod 600 .env    # this file has your DB password and JWT secret in it
```

### Production configuration guard

The backend validates its own configuration at startup and **refuses to
boot** — not just warns — if `ENVIRONMENT=production` (already set in
`.env.production.example`) and any of these are true: `JWT_SECRET_KEY` is
still the placeholder value or under 32 characters, `CORS_ALLOW_ORIGINS`
contains a wildcard (`*`), or `ENCRYPTION_KEY` is missing/malformed. If step
6 below fails immediately with a message like "Refusing to start with an
insecure production configuration", the error lists every specific field
that needs fixing — fix all of them and re-run `docker compose ... up`
again, no need to fix-and-redeploy one at a time.

## 6. Build and start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes a few minutes (compiling/installing dependencies,
building the frontend bundle). Caddy will request its HTTPS certificate
automatically on first start — watch for it:

```bash
docker compose -f docker-compose.prod.yml logs -f caddy
```

You should see lines mentioning `certificate obtained successfully`. If you
instead see ACME/challenge errors, double check step 2 (DNS must already
resolve to this VM, and ports 80/443 must be reachable from the internet —
test with `curl -I http://<VM_IP>` from your own machine).

## 7. Run database migrations

The `migrate` service is defined but not auto-started (so a bad migration
never blocks the whole stack from starting) — run it explicitly once the
`db` container is healthy:

```bash
docker compose -f docker-compose.prod.yml run --rm migrate
```

### Zero-downtime migrations (once you're running more than one backend instance)

On a single VM with `restart: unless-stopped` and no rolling deploy, a
migration + restart causes a brief (seconds-long) gap regardless — fine for
this scale. It stops being fine the moment you run more than one `backend`
replica (see "Scaling notes" below) and deploy them one at a time: for a
window during that rollout, **old and new application code run against the
same schema simultaneously**. A migration that isn't backward-compatible
with the *previous* release will break the old replicas before they've
finished draining.

The standard fix is the **expand/contract pattern**, split across two
separate deploys:

1. **Expand** (ships with the new code, but doesn't require it): add the
   new column as nullable (or with a default), add the new table, add the
   new index — anything purely additive. Old code ignores the new column;
   new code can start writing to it. Never rename or drop anything in this
   step.
2. **Backfill** (if needed): a one-off script/task populates the new
   column for existing rows, run after step 1's migration but decoupled
   from any single deploy.
3. **Contract** (a *later* deploy, once you're certain no replica running
   the old code is still live): now it's safe to add the `NOT NULL`
   constraint, drop the old column, rename things, etc.

Concretely in this codebase: `alembic/versions/` is already one small
migration per logical change (see the `0001`...`0006` history) rather than
one giant migration per phase — keep that granularity, and when a change
isn't purely additive, split it into an expand migration now and a contract
migration in a follow-up deploy instead of doing both in one step. The
`migrate` service's isolation (a one-off `run --rm`, never part of the
`backend`/`celery_worker` startup path) is what makes this safe to run
*before* the new backend image goes live — migrations and code rollout are
already decoupled here, which is the other half of doing this safely.

## 8. Verify

```bash
curl https://bank.example.com/health
curl https://bank.example.com/ready
```

Both should return `{"status":"ok", ...}`. Open `https://bank.example.com`
in a browser — you should see the login page over a real, valid HTTPS
certificate (padlock, no warnings). Register an account and confirm the
dashboard loads.

`https://bank.example.com/docs` gives you the interactive Swagger UI
against the real deployed API.

## 9. Observability — metrics

`GET /metrics` (proxied by Caddy, or reachable directly on the `backend`
container's port 8000 from inside the VM) exposes Prometheus-format
metrics: HTTP request counts/latency, rate-limit rejections, email/SMS
delivery success/failure, and transfer outcomes. It's already correctly
aggregated across all `gunicorn` worker processes (see `backend/README.md`'s
Phase 9 notes for how that was verified) — no per-worker scrape confusion.

To actually collect and visualize it, point a Prometheus instance at it —
the minimal addition is a `prometheus` service in a docker-compose override
(not included here, since running one is optional and adds another
container to operate):

```yaml
# docker-compose.observability.yml (example — not included by default)
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"
```

```yaml
# prometheus.yml
scrape_configs:
  - job_name: banking-backend
    static_configs:
      - targets: ["backend:8000"]
```

Run alongside the main stack with
`docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml up -d`.
From there, Grafana (pointed at this Prometheus as a data source) and
Alertmanager (for on-call paging) are the next two pieces — both are
genuinely your call on rules/dashboards/thresholds, so they're not
prescribed here. OpenTelemetry tracing isn't wired in at all yet; every
request already carries an `X-Request-ID` header that a trace span could
reuse as its trace ID if you add one later.

## 10. Set up automated database backups

```bash
chmod +x backup-db.sh
./backup-db.sh                     # test it manually first

crontab -e
# add this line — daily at 3am server time:
0 3 * * * /home/ubuntu/online-banking/backup-db.sh >> /home/ubuntu/backup.log 2>&1
```

Backups land in `~/banking-backups/`, gzipped, with the last 14 days kept
automatically. Copy them off the VM periodically (e.g. to S3/Spaces) —
a backup that only ever lives on the same disk as the database it's
backing up doesn't protect you from losing that disk.

## 11. Deploying updates later

```bash
cd online-banking
git pull                                              # or re-upload the new zip
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm migrate   # if there are new migrations
```

Each service has `restart: unless-stopped`, so the stack also survives a VM
reboot on its own — no need to re-run anything after e.g. a provider-side
maintenance restart.

(If you've since scaled to multiple `backend` replicas, see step 7's
"Zero-downtime migrations" section before writing a migration that isn't
purely additive.)

## Day-2 operations

```bash
# Tail logs for one service
docker compose -f docker-compose.prod.yml logs -f backend

# Check everything's up
docker compose -f docker-compose.prod.yml ps

# Open a shell in the backend container (e.g. to run a one-off script)
docker compose -f docker-compose.prod.yml exec backend bash

# Stop everything (data volumes are preserved)
docker compose -f docker-compose.prod.yml down

# Nuclear option — also deletes all data (Postgres, Redis, Caddy certs)
docker compose -f docker-compose.prod.yml down -v
```

## Scaling notes (when you outgrow one VM)

This single-VM setup comfortably handles a meaningful amount of real
traffic, but if you need to grow further: `backend` and `celery_worker` are
already stateless and horizontally scalable (`docker compose up -d --scale
celery_worker=3`, or move to a managed container platform); the real
constraint at that point is usually the single Postgres instance, at which
point a managed Postgres service (RDS/Cloud SQL/DigitalOcean Managed DB)
with connection pooling is the natural next step — swap `DATABASE_URL` to
point at it and nothing in the application code needs to change.

## What this guide does *not* cover

- **Multi-region / high-availability** setups — this is a single-VM
  deployment; a VM outage means downtime until it's restarted.
- **WAF / DDoS protection** — consider putting Cloudflare (or your
  provider's equivalent) in front of the domain if this will be
  internet-facing at any real scale.
- **Secrets management beyond a `.env` file** — fine for a single VM; see
  `backend/app/core/secrets_provider.py` for the integration seam to
  Vault/AWS Secrets Manager/GCP Secret Manager once you move to multiple
  VMs/containers (not wired to a real backend — this sandbox has no network
  path to test one against).
- **PCI-DSS certification** — this codebase implements PCI-adjacent
  practices (masked card numbers, encrypted 2FA secrets, Argon2 password
  hashing, audit logging, TLS everywhere, rate limiting), but actual PCI-DSS
  compliance is a certification, not a code property: it requires a
  Qualified Security Assessor's formal audit against your *specific*
  deployment, data flows, and organizational processes. Don't treat
  anything in this repo as a substitute for that engagement if you'll
  actually be handling real cardholder data.
- **External penetration test** — get one before handling real money. This
  codebase has been reasoned about and tested by its own author (an AI, in
  this case) — that is structurally not the same thing as an adversarial
  review by an independent third party, no matter how thorough the former
  was.
- **The actual first `docker compose up` on real infrastructure** — every
  piece of this stack has been verified as thoroughly as possible without a
  running Docker daemon (config validation, direct-process smoke tests
  against real Postgres/Redis — see `backend/README.md`'s Phase 6-9 notes
  for specifics), but the literal `docker build` + container orchestration
  path has not been exercised end-to-end. Budget time for first-deploy
  surprises regardless of how much has been pre-verified.
