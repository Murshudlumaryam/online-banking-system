# Online Banking System — Backend (Faza 1-3)

Bu README Fazə 1, 2 və 3-ü əhatə edir: Docker fundamentı, `core`, `db`,
`shared`, `auth`+`users`, `customers`, `accounts`, `cards`, `exchange_rates`,
`beneficiaries`, `transactions`+`ledger_entries`, `audit_logs`,
`background_tasks`.

## Nə tamamlandı

### Faza 1
- **core**: konfiqurasiya (`pydantic-settings`), Argon2 parol hash-i, JWT access
  token + opaque refresh token (rotasiya ilə), mərkəzləşdirilmiş domain
  exception-ları və handler-lər, struktur (JSON) loglama, request-id +
  rate-limit ASGI middleware
- **db**: async SQLAlchemy 2.x engine/session (asyncpg), `Base` + UUID/timestamp/
  soft-delete mixin-ləri
- **users**: `User` modeli (`ADMIN`/`CUSTOMER` rolu), repository
- **customers**: minimal `Customer` modeli (register axını üçün)
- **auth**: `/api/v1/auth/register|login|refresh|logout|password/change|
  password/reset-request|password/reset-confirm` — tam işləyən servis
  qatı, refresh token rotasiyası + təkrar istifadə aşkarlanması, self-contained
  JWT əsaslı parol bərpası
- **audit_logs**: minimal append-only model + yazma servisi
- **background_tasks**: Celery konfiqurasiyası + audit log / bildiriş task-ları
- **Alembic**: `0001_initial_phase1` miqrasiyası

### Faza 2
- **customers**: tam profil idarəetməsi — `GET/PATCH /api/v1/customers/me`,
  `GET /api/v1/customers/me/dashboard` (hesab siyahısı + valyuta üzrə balans
  cəmi)
- **accounts**: `Account` modeli, `GET /api/v1/accounts`,
  `GET /api/v1/accounts/{id}`, `GET /api/v1/accounts/{id}/balance` —
  ownership dependency-si ilə (`get_owned_account`, 404 — mövcudluğu
  sızdırmır)
- **cards**: `Card` modeli (maskalanmış PAN, `Card.mask()`),
  `GET /api/v1/cards`, `GET /api/v1/cards/{id}` — eyni ownership nümunəsi
- **Alembic**: `0002_phase2_accounts_cards` miqrasiyası

### Faza 2 zamanı aşkarlanıb düzəldilmiş real bug
`confirm_password_reset` metodunda `verify_password_reset_token()` çağırışı
`try/except` daxilində deyildi — nəticədə artıq istifadə olunmuş/etibarsız
reset token 500 (gözlənilməyən server xətası) qaytarırdı, düzgün 401 əvəzinə.
Real Postgres-ə qarşı tam test dəsti işlədilərkən aşkarlandı və düzəldildi;
indi ayrıca `InvalidResetTokenError` (`INVALID_RESET_TOKEN`) domain
exception-ı istifadə olunur.

### Faza 3
- **exchange_rates**: `ExchangeRate` modeli, aktiv məzənnə axtarışı,
  `GET /api/v1/exchange-rates` (müştəri üçün oxu-yalnız)
- **beneficiaries**: tam CRUD (`POST/GET /api/v1/beneficiaries`,
  `PATCH/DELETE /api/v1/beneficiaries/{id}`) — hesab nömrəsinin sistemdə
  mövcud olduğunu yoxlayır, soft-delete
- **transactions** + **ledger_entries**: bank sisteminin nüvəsi —
  - `POST /api/v1/transactions/transfer` — ownership/status/balans/məzənnə
    validasiyası, PENDING tranzaksiya + OTP yaradılması
  - `POST /api/v1/transactions/{id}/confirm` — OTP təsdiqi, **pessimistic
    locking** (`SELECT ... FOR UPDATE ORDER BY id` — deadlock-un qarşısını
    almaq üçün), balanced double-entry ledger qeydləri, tək DB tranzaksiyası
    daxilində ACID təminatı
  - `GET /api/v1/transactions`, `/{id}`, `/search?reference=` — pagination
    ilə (`shared/schemas.py`-dəki `PaginatedResponse` bu fazada ilk dəfə
    işə düşdü)
  - OTP: 6 rəqəmli kod, SHA-256 hash, 5 dəqiqə etibarlılıq, maksimum 5 səhv
    cəhd — kod heç vaxt HTTP cavabında və ya log-da görünmür, yalnız
    (stub) bildiriş kanalı vasitəsilə
- **Alembic**: `0003_phase3_transactions` miqrasiyası

### Faza 3 zamanı aşkarlanıb düzəldilmiş real bug (race condition)
Xüsusi yazılmış **real paralellik testi** (`test_concurrency.py` — iki
müstəqil DB bağlantısı ilə eyni tranzaksiyanı eyni anda təsdiqləməyə cəhd
edir) 5 dəfədən 1-ində uğursuz olurdu: uduzan paralel sorğu, qalib artıq
`SUCCESS` etdiyi tranzaksiyanın üzərinə səhvən `FAILED` yazırdı (öz
"balans kifayət etmir" defensive yoxlaması zamanı). Bu, maliyyə
qeydlərinin bütövlüyünü pozan ciddi bir bugdur. Düzəliş:
`confirm_transfer`-in xəta emalı indi əvvəlcə tranzaksiyanın **hələ də
PENDING** olduğunu yoxlayır — əgər paralel sorğu artıq onu həll edibsə,
mövcud nəticəni əvəz etmək əvəzinə `TransactionAlreadyProcessedError`
qaytarır. Düzəlişdən sonra test 20/20 stabil keçdi.

### Faza 4
- **admin**: tam admin əməliyyatları — hamısı `require_admin` (RBAC) ilə
  qorunur və hər əməliyyat audit log yazır:
  - `GET /api/v1/admin/customers` (+ status filtri), `GET /{id}`,
    `PATCH /{id}/status` (aktivləşdir/blokla, müştəriyə bildiriş göndərir)
  - `GET /api/v1/admin/accounts` (+ status filtri),
    `POST /api/v1/admin/accounts` (hesab yaradır), `PATCH /{id}/status`
  - `POST /api/v1/admin/cards` (Luhn-etibarlı sintetik PAN generasiyası),
    `PATCH /{id}/block`
  - `GET /api/v1/admin/transactions` (+ status filtri), `GET /{id}`
    (ledger qeydləri ilə)
  - `GET /api/v1/admin/audit-logs` (`user_id`/`action`/`resource_type`/
    tarix aralığı üzrə filtr, pagination)
  - `GET/POST /api/v1/admin/exchange-rates` (admin görünüşü qeyri-aktiv
    məzənnələri də göstərir)
- **audit_logs**: tam oxu/axtarış qatı (`AuditLogRepository`) admin router-ə
  qoşuldu
- **background_tasks**: `expire_stale_transactions_task` — OTP-si vaxtı
  keçmiş, lakin müştəri tərəfindən tərk edilmiş PENDING tranzaksiyaları
  avtomatik `FAILED`-ə keçirən Celery Beat periodic task (hər 60 saniyədə);
  `docker-compose.yml`-ə ayrıca `celery_beat` servisi əlavə olundu
- Yeni miqrasiya tələb olunmadı (admin modulu mövcud cədvəllərdən istifadə edir)

### Faza 4 zamanı aşkarlanıb düzəldilmiş problemlər
- `AuditLogResponse`-də `ip_address` sahəsi: Postgres-in `INET` sütunu
  Python-da `ipaddress.IPv4Address` obyekti qaytarır, `str` deyil —
  Pydantic bunu avtomatik çevirmir və validasiya xətası verirdi.
  `field_validator(mode="before")` ilə düzəldildi.
  - Bu, `test_write_audit_log_async_persists_entry` testində (Faza 3-dən
    qalma) də eyni səbəbdən oxşar formada aşkarlanmışdı.
- `create_exchange_rate` / `create_account`: commit-dən sonra `refresh()`
  çağırılmadığı üçün Decimal dəyərləri DB-nin `NUMERIC` dəqiqliyini deyil,
  sorğuda göndərilən orijinal formatı (`"1.85"` və `"0"` kimi) qaytarırdı.
  Digər fazalardakı eyni problem kimi `refresh()` əlavə olunaraq düzəldildi.

## Test əhatəsi (yenilənib)

Tam test dəsti: **66/66 keçdi** (real PostgreSQL-ə qarşı), ümumi əhatə
**92%**. Bütün Fazə 1-4 biznes-məntiq modulları 83–100% aralığındadır.
Fazə 4-ün əlavə etdiyi testlər: RBAC (customer admin endpoint-lərinə giriş
edə bilmir), müştəri/hesab/kart/məzənnə tam idarəetmə axını, admin-in
hesabı blokladıqdan sonra müştərinin köçürmə edə bilməməsi (cross-module
inteqrasiya yoxlaması), audit log axtarışının filtrləri (user_id, action)
düzgün tətbiq etdiyinin real seed data ilə yoxlanması, və periodic
housekeeping sweep-in PENDING+vaxtı-keçmiş tranzaksiyaları düzgün
`FAILED`-ə keçirdiyi.

## Necə işə salmaq olar

```bash
cp .env.example .env      # JWT_SECRET_KEY-i mütləq dəyişdirin
docker compose up --build
```

Miqrasiyaları tətbiq etmək:

```bash
docker compose exec backend alembic upgrade head
```

Swagger sənədləşməsi: `http://localhost:8000/docs`
Health / readiness: `http://localhost:8000/health`, `http://localhost:8000/ready`

## Testləri işə salmaq

Testlər **real PostgreSQL** tələb edir (Postgres-a xas UUID/JSONB/ENUM tipləri
istifadə olunduğu üçün SQLite ilə əvəzlənmir):

```bash
docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://banking_user:banking_pass@db:5432/banking_test_db \
  backend pytest -v

# with coverage (requires .coveragerc's `concurrency = greenlet` to get
# accurate numbers for async SQLAlchemy code — see note below)
docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://banking_user:banking_pass@db:5432/banking_test_db \
  backend pytest --cov=app --cov-report=term-missing
```

(Testdən əvvəl `banking_test_db` adlı ayrıca bir database yaradılmalıdır;
məsələn `docker compose exec db createdb -U banking_user banking_test_db`.)

## Bilinən məhdudiyyət

Gözlənilməyən (500) xətalarda `X-Request-ID` başlığı cavaba əlavə olunmaya
bilər — çünki bu xətalar Starlette-in `ServerErrorMiddleware`-i tərəfindən bizim
request-id middleware-dən *kənarda* tutulur. Domain (biznes) xətalarının
hamısında (400/401/403/404/409/422/429) bu başlıq düzgün əlavə olunur; yalnız
tam gözlənilməyən sistem xətaları bu kənar hala düşür. Bu, production
monitorinqinə görə qəbul edilə bilər səviyyədədir və Faza 6-da (sərtləşdirmə)
nəzərdən keçiriləcək.

## Faza 5 (Frontend)

React + Vite + TypeScript + internal SPA router + React Query + TailwindCSS —
tam müştəri və admin UI-si. Ətraflı: `frontend/README.md` (dizayn sistemi,
autentifikasiya axını, test nəticələri, məlum məhdudiyyətlər).

Doğrulanmış: `tsc -b` (strict) səhvsiz, `vite build` uğurlu, ESLint 0
xəbərdarlıqla keçir, **28/28 Vitest testi keçir**. Doğrulama zamanı tapılıb
düzəldilmiş bug: `formatMoney`-in fallback yolu səhv test edilirdi ("XXX"
əslində etibarlı ISO 4217 kodu olduğu üçün heç vaxt catch budağına
çatmırdı) — test düzgün formalaşdırılmamış koda ("AB") dəyişdirildi.

## Faza 6 (Sərtləşdirmə)

- **Rate limiting**: Redis-backed fixed-window limiter (`app/core/rate_limiter.py`)
  — çoxlu backend worker prosesi arasında düzgün işləyir (in-memory versiya
  hər worker-də ayrıca sayğac saxlayıb limiti sükutla çoxaldardı). Redis
  əlçatmaz olduqda **fail-open** strategiyası (xəbərdarlıq logu ilə icazə
  verir) — rate limiting kömürlük xətti nəzarətidir, Redis-in qısa fasiləsi
  bütün API-ni dayandırmamalıdır. Endpoint-ə görə fərqli limitlər:
  login (10/dəq), register (5/dəq), parol-bərpa sorğusu (3/dəq),
  köçürmə (20/dəq), ümumi (120/dəq).
- **Security headers**: `SecurityHeadersMiddleware` — `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`,
  `Strict-Transport-Security`, `Cross-Origin-Opener-Policy` hər cavaba
  əlavə olunur.
- **`/ready`** indi Redis bağlantısını da yoxlayır (əvvəllər yalnız DB).
- **OpenAPI/Swagger cilalanması**: tam tag təsvirləri, əlaqə/lisenziya
  metadata-sı, Bearer token üçün "Authorize" düyməsi `/docs`-da işləyir
  (`HTTPBearer` security scheme avtomatik qeydiyyatdan keçir).
- **mypy** (strict-ə yaxın konfiqurasiya) bütün `app/` üzərində
  **səhvsiz keçir** — doğrulama zamanı 19 real tip xətası tapılıb
  düzəldildi (aşağıda).
- **pip-audit**: təcrid olunmuş venv-də (yalnız `requirements.txt`)
  aparılan audit **1 qalan tapıntı** göstərir: `ecdsa` (python-jose-nin
  keçidli asılılığı) — Minerva timing atağı, layihə tərəfindən "düzəliş
  planlaşdırılmır" kimi qeyd olunub. Bizim JWT konfiqurasiyamız yalnız
  **HS256** (HMAC, ECDSA yox) istifadə etdiyi üçün bu kod yolu heç vaxt
  icra olunmur — qəbul edilmiş, sənədləşdirilmiş risk. Digər 4 zəiflik
  (`python-jose`, `python-multipart`, `starlette`, `pytest`) versiya
  yüksəldilməsi ilə düzəldildi (aşağıda).
- **CI/CD**: `.github/workflows/ci.yml` — backend lint (ruff) + type-check
  (mypy) + test (Postgres+Redis service container-ləri ilə) + security scan
  (pip-audit) + frontend lint (eslint) + type-check/build (tsc+vite) + test
  (vitest) + audit (npm audit) + hər iki Docker image-in build yoxlanması.

### Faza 6 zamanı aşkarlanıb düzəldilmiş problemlər

1. **mypy 19 real xəta tapdı**, hamısı düzəldildi:
   - `AuthService._issue_token_pair`-in `return_row: bool` parametrinə görə
     iki fərqli formada (tuple/tək dəyər) qaytarması — mypy-ın tuş vurduğu
     əsl dizayn qüsuru idi. Metod indi **həmişə tuple qaytarır**, çağıran
     tərəf destructuring edir (təmiz refactor, hack deyil).
   - Modellər arası forward-reference-lər (`Mapped["Customer"]` və s.)
     `# noqa: F821` ilə ruff-u susdururdu, amma mypy adları həqiqətən həll
     edə bilmirdi — `TYPE_CHECKING` importları ilə düzgün həll edildi.
   - `python-jose`-nin stub-sız `jwt.encode/decode` çağırışlarından
     `Any` qaytarılması, Redis `INCR`-in `Any` qaytarması, `Decimal`-ın
     `as_tuple().exponent`-inin `int | Literal['n','N','F']` union tipi —
     hamısı explicit tip daraltma ilə düzəldildi.
   - Pure ASGI middleware-lərdə `Message` tipinin səhv (`dict`) elan
     olunması.
2. **pip-audit 4 real zəiflik tapdı** (`python-jose` 3.3.0→3.5.0,
   `python-multipart` 0.0.9→0.0.32, `starlette` 0.38.6→1.3.1 — bunun üçün
   `fastapi` 0.115.0→0.139.1-ə yüksəldildi, `pytest` 8.3.3→9.0.3 +
   uyğun `pytest-asyncio` 0.24.0→1.4.0). Böyük versiya sıçrayışına
   baxmayaraq **tam test dəsti (84/84) və mypy dəyişiklikdən sonra da
   səhvsiz keçdi** — nəzəri uyğunluq fərziyyəsi deyil, faktiki doğrulama.
3. Starlette yenilənməsi bir `DeprecationWarning` üzə çıxardı
   (`HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT`) —
   düzəldildi.

### Yenilənmiş test əhatəsi

**84/84 test keçdi**, ümumi əhatə **93%**. Yeni testlər: Redis + in-memory
rate limiter (limit tətbiqi, müstəqil açarlar, pəncərə bitməsi, fail-open,
**real `/auth/login` endpoint-inin 429 qaytardığının HTTP səviyyəsində
doğrulanması**), security headers, `/health`+`/ready` (DB/Redis əlaqə
xətası halları daxil), admin modulunun 404 kənar halları.

## Faza 7 (Gələcək genişlənmə)

- **2FA (TOTP, RFC 6238)**: `POST /auth/2fa/setup` (sirr + `otpauth://` provisioning URI
  yaradır) → `POST /auth/2fa/enable` (authenticator app-dan kodu təsdiqləyir) →
  bundan sonra `POST /auth/login` tokens əvəzinə `mfa_required: true` +
  qısaömürlü (5 dəq) `challenge_token` qaytarır → `POST /auth/2fa/verify-login`
  (challenge_token + TOTP kodu) həqiqi tokenləri verir. `POST /auth/2fa/disable`
  həm parol, həm cari TOTP kodu tələb edir. `pyotp` istifadə olunur, saat
  meyli üçün ±1 addım (`valid_window=1`) tolerantlığı var.
- **PDF hesab çıxarışları**: `GET /accounts/{id}/statement?start_date&end_date`
  — `reportlab` (Platypus/Table) ilə generasiya olunan real PDF, ledger
  qeydlərini debit/kredit sütunlarında göstərir. Defolt: son 30 gün.
- **Real email inteqrasiyası**: `EmailProvider` abstraksiyası —
  `ConsoleEmailProvider` (defolt, yalnız log yazır) və `SMTPEmailProvider`
  (`aiosmtplib` ilə istənilən standart SMTP serverinə — SendGrid, SES,
  Postmark və s. — real göndərmə). `EMAIL_BACKEND=smtp` + `SMTP_*`
  dəyişənləri ilə kod dəyişikliyi olmadan aktivləşir. SMS inteqrasiyası
  bu fazada edilmədi (ödənişli gateway tələb edir) — sənədləşdirilmiş
  log-only stub olaraq qalır.
- **Planlaşdırılmış/təkrarlanan ödənişlər**: `POST /scheduled-payments`
  (DAILY/WEEKLY/MONTHLY) — yaradılış zamanı verilmiş səlahiyyətə əsaslanır,
  hər icrada yenidən OTP tələb etmir. Celery Beat hər 5 dəqiqədə bir vaxtı
  çatmış planları icra edir (`execute_scheduled_payments_task`), hər biri
  müstəqil idarə olunur (biri uğursuz olsa, digərlərini bloklamır).
- Yeni miqrasiyalar: `0004_phase7_2fa`, `0005_phase7_scheduled_payments`

### Faza 7 zamanı aşkarlanıb düzəldilmiş problemlər
1. **Əvvəldən mövcud bug**: `request_password_reset` bildiriş çağırışında
   `user_id` yerinə səhvən `reset_token` ötürülürdü (Faza 1-dən qalma).
   Real email inteqrasiyası bunu üzə çıxardı — `AuthService.request_password_reset`
   indi `(user_id, token)` tuple qaytarır, router düzgün `user_id` ötürür.
2. **Test mühiti kəşfi**: fon tapşırıqları (`AsyncSessionLocal`) production
   `DATABASE_URL`-dan istifadə edir — real Docker Compose-da düzgün işləyir,
   lakin lokal ad-hoc test icrasında `DATABASE_URL`-i `TEST_DATABASE_URL`
   ilə eyni təyin etmək lazımdır (CI-da artıq düzgün konfiqurasiya edilib).
3. **pytest-asyncio + connection pool**: modul-səviyyəli `AsyncSessionLocal`-ın
   connection pool-u testlər arasında saxlanılır, halbuki hər test öz
   event loop-unu alır — nəticədə "attached to a different loop" xətası.
   Hər testdən sonra bu engine-i `dispose()` edən avtomatik fixture əlavə
   olundu.
4. **Dizayn dəqiqləşdirməsi**: `otp_verified` sahəsi əvvəlcə paylaşılan
   `mark_success()`-də həmişə `True` təyin olunurdu — planlaşdırılmış
   ödənişlər üçün bu semantik cəhətdən yanlış idi (OTP həqiqətən
   yoxlanılmayıb). İndi yalnız interaktiv `confirm_transfer` yolunda
   `True` təyin olunur.
5. **pip-audit**: yeni asılılıqlardan `aiosmtplib` 3.0.2-də real bir
   zəiflik (SMTP command injection, CWE-93) aşkarlandı — 5.1.2-yə
   yeniləndi, real yerli SMTP server testi ilə yenidən doğrulandı.

### Test əhatəsi (final)
**116/116 test keçdi**, ümumi əhatə **94%**. mypy 87 fayl üzərində
səhvsiz, ruff təmiz. Yeni testlər arasında: tam 2FA enrollment→login axını,
real yerli SMTP serverə çatdırma (aiosmtpd ilə), PDF-in faktiki bytes
generasiya etdiyinin yoxlanılması, planlaşdırılmış ödəniş sweep-inin
uğur/uğursuzluq hallarının real commit edilmiş məlumatla doğrulanması.

## Faza 8 (SMS gateway, OpenAPI client, e2e)

- **Real SMS gateway**: `app/core/sms.py` — `ConsoleSMSProvider` (defolt)
  və `TwilioSMSProvider` (Twilio-nun REST API-sinə `httpx` ilə birbaşa
  HTTP çağırışı, rəsmi SDK əlavə etmədən). `SMS_BACKEND=twilio` +
  `TWILIO_*` dəyişənləri ilə aktivləşir. Bildiriş tapşırığı (`send_notification_task`)
  indi `sms` kanalını da real şəkildə emal edir — müştərinin telefon
  nömrəsini `Customer` cədvəlindən tapıb göndərir.
- **OpenAPI-dən TypeScript client generasiyası**: `scripts/export_openapi.py`
  — server işə salmadan, DB-yə qoşulmadan `app.openapi()`-ni birbaşa JSON-a
  çıxarır. Frontend-də `npm run generate:api` bu JSON-u `openapi-typescript`-dən
  keçirib tam tipli sxem yaradır. Ətraflı: `frontend/README.md`.
- **Playwright e2e**: `frontend/e2e/` — real brauzer, real backend, real
  Postgres/Redis ilə tam UI axınları (qeydiyyat→giriş→köçürmə+real OTP
  təsdiqi→admin panel). OTP/admin/balans üçün yalnız `ENVIRONMENT=test`
  olduqda aktivləşən, istehsalatda 404 qaytaran üç debug endpoint əlavə
  olundu (`app/core/test_mode.py`, `app/core/test_otp_store.py`).

### Faza 8 zamanı aşkarlanıb düzəldilmiş real bug
Real, çoxlu-sorğulu mühitdə (pytest-in paylaşılan session arxitekturası
xaricində) əl ilə apardığım tam e2e API doğrulaması zamanı tapıldı:
`debug-promote-to-admin` endpoint-i `UserRepository.save()` (yalnız
`flush()`) çağırırdı, lakin ardınca `session.commit()` etmirdi — nəticədə
rol dəyişikliyi sorğunun sessiyası bağlananda səssizcə geri qaytarılırdı.
Adi pytest testi bunu tuta bilməzdi (bütün sorğular üçün EYNİ session-u
paylaşdığından, `flush()` təkbaşına növbəti sorğuya "görünürdü"). Düzəldildi
və iki həqiqətən müstəqil DB bağlantısı istifadə edən xüsusi regression
testi ilə əhatə olundu (`test_debug_promote_to_admin_actually_persists_across_real_separate_connections`).

### Yenilənmiş test əhatəsi
**134/134 test keçdi**, ümumi əhatə **94%**, mypy 90 fayl üzərində
səhvsiz, ruff təmiz. Yeni testlər: SMS provider (real lokal HTTP server-ə
qarşı Twilio sorğu formatının doğrulanması), bildiriş marşrutlaşdırmasının
`sms` kanalı, 3 debug endpoint-in həm 404 (istehsalat rejimi), həm işlək
(test rejimi) halları, və yuxarıdakı real bug üçün regression testi.

## Faza 9 (Production hardening review-dən sonra)

Bu fazadakı hər maddə, layihənin xarici icra mühitində (Docker daemon
bağlı, Postgres yox) aparılan bir production-readiness review-un "qalan"
siyahısına cavabdır. Kodla həll oluna bilən hər şey tətbiq edilib və real
testlərlə doğrulanıb; insan/təşkilati proses tələb edən maddələr (aşağıda)
açıq şəkildə "edilməyib" olaraq qeyd olunur — saxta tamamlanma iddiası
yoxdur.

### Kodla tam həll olunanlar

- **Production weak-secret guard** (`app/core/config.py`): `ENVIRONMENT=production`
  olduqda tətbiq **başlamağı rədd edir**, əgər: `JWT_SECRET_KEY` defolt
  dəyərdədirsə və ya 32 simvoldan azdırsa, `CORS_ALLOW_ORIGINS`-də wildcard
  (`*`) varsa, və ya `ENCRYPTION_KEY` təyin olunmayıbsa/etibarsız Fernet
  açarıdırsa. Bütün pozuntular **eyni anda** bir xəta mesajında göstərilir
  (operator hər dəfə bir problemi düzəldib yenidən cəhd etməli olmasın deyə).
  Development rejiminə təsir etmir.
- **TOTP sirrinin şifrələnməsi at rest**: `app/core/crypto.py` (Fernet,
  `cryptography` paketi). `users.totp_secret` sütunu genişləndirildi
  (`0006_phase9_totp_encryption` miqrasiyası), bütün 2FA axını (setup/
  enable/disable/verify) indi şifrələnmiş formada saxlayır/oxuyur. **Real
  regression testi**: DB-dən sətri birbaşa oxuyub, saxlanılan dəyərin
  orijinal sirrə bərabər OLMADIĞINI və düzgün açarla deşifr olunduqda
  bərabər OLDUĞUNU yoxlayır (`test_totp_secret_is_encrypted_at_rest_in_the_database`).
- **Secrets provider abstraksiyası** (`app/core/secrets_provider.py`):
  Vault/AWS Secrets Manager/GCP Secret Manager üçün konkret inteqrasiya
  "reseptləri" ilə sənədləşdirilmiş `Protocol` — hazırkı `.env`-əsaslı
  model dəyişmədən, çoxlu VM-ə keçəndə real SDK-larla (real kimlik
  məlumatları bu sandbox-dan əlçatan olmadığı üçün tam SDK inteqrasiyası
  yazılmayıb, amma struktur işə hazırdır).
- **Full observability — metrics** (`app/core/metrics.py`, `GET /metrics`):
  Prometheus formatında HTTP sorğu sayı/latency, rate-limit rədd sayı,
  email/SMS çatdırma uğur/uğursuzluq sayı, transfer nəticələri.
  - **Doğrulama zamanı özüm tapıb düzəltdiyim real dizayn problemi**:
    `Dockerfile.prod`-da `gunicorn` çoxlu worker prosesi ilə işləyir —
    `prometheus_client`-in defolt in-memory registry-si **hər worker üçün
    ayrıdır**, yəni `/metrics` scrape-i həmişə TƏK bir worker-in qismən
    məlumatını qaytarardı (scrape-dən scrape-ə dəyişən, səhv rəqəmlərlə).
    Rəsmi multiprocess rejimini tətbiq etdim (`PROMETHEUS_MULTIPROC_DIR`,
    `gunicorn.conf.py`-dəki `child_exit` hook-u) və **real 3-worker
    gunicorn prosesi ilə** (Docker-siz, birbaşa) iki ayrı sessiyada
    yoxladım: 30 sorğu göndərib `/metrics`-i 3 dəfə ardıcıl scrape etdikdə
    hər dəfə eyni, düzgün cəmlənmiş `31.0` (30 + öncəki bir yoxlama sorğusu)
    göstərdiyini təsdiqlədim. Sonra bir worker-i `SIGTERM`-lə öldürüb
    (gunicorn avtomatik yenisini doğurdu) ölü worker-in töhfəsinin (`31.0`)
    itmədiyini, daha sonra göndərilən 4 əlavə sorğunun sağ qalan + yeni
    worker-lər üzərindən düzgün toplanaraq `35.0`-a çatdığını yoxladım.
  - Tracing (OpenTelemetry) və alerting (Alertmanager qaydaları) **tətbiq
    edilməyib** — hər ikisi real bir kolektor/on-call prosesi tələb edir ki,
    bu sandbox-dan yoxlanıla bilmir; hər HTTP sorğusunun artıq daşıdığı
    `X-Request-ID` (bax `core/middleware.py`) trace ID kimi təkrar istifadə
    oluna bilər — əsas hazırdır, tam simlər çəkilməyib.
- **Delivery monitoring (email/SMS)**: `app/core/email.py` və
  `app/core/sms.py`-dəki bütün provider-lər (`Console*` və real `SMTP`/
  `Twilio`) indi hər göndərmə cəhdini `notification_delivery_total{channel,
  outcome}` metrikinə yazır — real provider ilə çatdırma faizini
  Prometheus/Grafana-da izləmək mümkündür.

### Kodla həll olunmayan, insan/təşkilati proses tələb edən maddələr

Bunlar **bilərəkdən tətbiq edilməyib** — bir AI-pair-programming sessiyasının
səlahiyyəti xaricindədir və saxta "edildi" iddiası daha zərərli olardı:

- **PCI-DSS / maliyyə uyğunluq review-u**: kart məlumatları maskalanmış
  saxlanılır (bax `cards/models.py`), amma real PCI-DSS sertifikatlaşması
  akkreditə olunmuş bir QSA (Qualified Security Assessor) tərəfindən aparılan
  rəsmi audit tələb edir — kod səviyyəsində "tamamlandı" deyilə bilməz.
- **Xarici penetrasiya testi**: daxili təhlükəsizlik tədbirləri (rate
  limiting, Argon2, OTP, audit log, security header-lər) mövcuddur, amma
  bunların **kifayət qədər** olduğunu yalnız müstəqil, ixtisaslaşmış bir
  pentest komandası təsdiqləyə bilər.
- **Docker daemon işlək mühitdə tam integration/e2e test**: bu sandbox-da
  Docker daemon (və `docker` CLI-nin özü) yoxdur. Onun əvəzinə üç fərqli
  doğrulama apardım: (1) hər iki compose faylını **rəsmi compose-spec JSON
  schema-sına** (`compose-spec.json`, GitHub-dan real olaraq endirilib) qarşı
  doğruladım — hər ikisi keçdi; (2) hər iki faylda istifadə olunan bütün
  mühit dəyişənlərini (`POSTGRES_PASSWORD`, `POSTGRES_USER` kimi `:?`
  ilə **məcburi** işarələnənlər daxil) müvafiq `.env.example`/
  `.env.production.example` fayllarında mövcud olduğunu təsdiqlədim; (3)
  `gunicorn`+`UvicornWorker`-i **real 3-worker prosesi olaraq**, real
  Postgres/Redis-ə qarşı, `Dockerfile.prod`-dakı dəqiq CMD-i ilə birbaşa
  (Docker-siz) işə salıb tam qeydiyyat→2FA quraşdırma→MFA login axınının
  fərqli worker-lər arasında düzgün işlədiyini yoxladım (yuxarı bax). Amma
  faktiki `docker build`/`docker compose up` heç vaxt icra edilməyib. VM-də
  ilk `docker compose -f docker-compose.prod.yml up -d --build` icrası
  diqqətlə izlənilməlidir.
- **Migration strategiyası — zero-downtime**: `docker-compose.prod.yml`-də
  miqrasiyalar artıq ayrıca, `profiles: ["tools"]` ilə gizlədilmiş `migrate`
  servisi kimi işləyir (backend/celery başlamazdan əvvəl blok etmir) — bu,
  düzgün istiqamətdir, amma **əlavə** sxem dəyişiklikləri backward-compatible
  olmalıdır (məs. yeni sütun `NOT NULL` olmadan əlavə edilməli, sonra
  backfill, sonra `NOT NULL` constraint) ki, köhnə kod işlədiyi zaman yeni
  miqrasiya onu qırmasın. Detallı "expand-contract" strategiyası
  `DEPLOYMENT.md`-yə əlavə olundu, amma real multi-instance zero-downtime
  deploy-un özü sınaqdan keçirilməyib (bir VM-lik quraşdırmada bu hələ
  kritik deyil).

### Test əhatəsi (yenilənib)

**157/157 test keçdi** (32 yenisi bu fazada əlavə olundu — o cümlədən
`render_metrics()`-in tək-proses/multiprocess qollarının hər ikisini əhatə
edən 2 test), ümumi əhatə
**94%**, mypy 93 fayl üzərində səhvsiz, ruff təmiz. `pip-audit` yenidən
işlədildi: yeni `cryptography` asılılığında **2 real CVE tapıldı** (buffer
overflow + statically-linked OpenSSL zəifliyi, 46.0.6 versiyasında) —
`48.0.1`-ə yüksəldildi, bütün test dəsti yenidən işlədilərək heç nəyin
pozulmadığı təsdiqləndi. Qalan yeganə tapıntı əvvəlki fazalardan sənədləşmiş
`ecdsa` (qəbul edilmiş risk, HS256 istifadə etdiyimiz üçün kod yolu aktiv
deyil).

## Növbəti addım

Bütün planlaşdırılan fazalar (1-9) tamamlandı. Mümkün gələcək istiqamətlər:
real Vault/AWS Secrets Manager inteqrasiyası (real kimlik məlumatları ilə),
OpenTelemetry tracing, Alertmanager qaydaları, real PCI/pentest prosesi,
VM-də faktiki ilk `docker compose up` icrasının izlənilməsi.

## Phase 10 - Audit Blocker Fixes

This phase addresses the production-readiness blockers found in the final audit:

- Transaction race condition fixed: `TransactionService.confirm_transfer` now locks the transaction row with `SELECT ... FOR UPDATE` before moving money and re-checks `PENDING` while locked. Two concurrent OTP confirmations for the same transaction can no longer execute the same transfer twice.
- Atomic confirmation: the inner success-path commit was removed. OTP verification, transaction status, account balances, and ledger entries are persisted in one database commit.
- Ledger duplicate protection: `ledger_entries` now has `uq_ledger_entries_transaction_account_type`, added by migration `0007_ledger_entry_uniqueness`.
- Regression coverage: the concurrency test now seeds sender balance with `2 * amount`, so a real double-execution bug would be caught even when the account has enough money for two debits. It also asserts exactly two ledger rows.
- Deposit/withdrawal: admin-only `POST /api/v1/admin/accounts/{id}/deposit` and `POST /api/v1/admin/accounts/{id}/withdraw` were added. Both lock the account row, validate account status/currency/balance, and write an `account_cash_operations` audit row with `balance_before` and `balance_after`. Migration: `0008_account_cash_operations`.
- Account statements: generated PDF statements now include both ledger transfer entries and admin cash deposit/withdrawal operations.
- Refresh token storage hardening: login/MFA/refresh now set access and refresh tokens as HttpOnly cookies. The frontend no longer stores refresh tokens in `localStorage`; session bootstrap uses `GET /api/v1/auth/session`. Bearer token support remains for API and e2e compatibility.
- Docker hygiene: obsolete Compose `version` keys were removed and backend/frontend `.dockerignore` files were added.

### Phase 10 Verification Status

Verified in this environment:

```bash
cd frontend
npm run build
npm run lint
npm test -- --run
npm audit

cd ..
python -m compileall -q backend/app backend/tests
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.prod.yml config --quiet
```

Results: frontend build/lint/tests passed, `npm audit` reported 0 vulnerabilities, backend compile passed, and both Compose configs are syntactically valid.

Docker build/run and Playwright e2e could not be physically completed on this machine because Docker Desktop cannot start (`Docker Desktop is unable to start`, missing `dockerDesktopLinuxEngine` pipe). Run these on a Docker-enabled VM/runner:

```bash
docker compose -f docker-compose.prod.yml build backend frontend
docker compose --profile test up -d test_db redis
docker compose exec backend alembic upgrade head
docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://banking_user:banking_pass@test_db:5432/banking_test_db backend pytest -v
cd frontend && npx playwright test
```
