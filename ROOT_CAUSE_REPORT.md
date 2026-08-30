# Root-Cause Hesabatı — OTP, Authentication və Transaction Flow Auditi

## Ön qeyd — Mərhələ 1 analizinin nəticəsi

Kod tam analiz edildikdən sonra tapşırığın fərz etdiyi əsas ssenari ilə **real arxitektura arasında fərq** aşkar edildi:

| Sənədin fərziyyəsi | Real vəziyyət (koda əsasən) |
|---|---|
| Registration OTP mövcuddur | **Yoxdur** — qeydiyyat OTP-siz, birbaşadır |
| Login email/SMS OTP mövcuddur | **Yoxdur** — login yalnız parol + könüllü TOTP (Google Authenticator) istifadə edir |
| 3 OTP növü (Registration/Login/Transaction) bir-birinə qarışır | Yalnız **1 real OTP növü** var (Transaction) — `TransferConfirmation.transaction_id` **UNIQUE FK** ilə bağlı olduğu üçün qarışma arxitektura səviyyəsində mümkün deyil |

## 1. Root Cause

### Problem 1: "OTP kodu Gmail-ə gəlmir"
**Səbəb:** `initiate_transfer` funksiyası OTP-ni hardcoded olaraq yalnız `"sms"` kanalı ilə göndərirdi. Email üçün heç bir çatdırılma yolu yox idi.
**Fayl:** `backend/app/modules/transactions/service.py`

### Problem 2: Strukturlaşdırılmış OTP logging-i "işləmirdi"
**Səbəb:** `JsonFormatter` bərk kodlanmış icazə siyahısına (`request_id`, `user_id`, `error_code`, `path`, `module`) malik idi — bundan kənar hər hansı `extra` sahəsi səssizcə atılırdı.
**Fayl:** `backend/app/core/logging.py`

### Problem 3: Qəbul edən tərəf göndərənin OTP-sini idarə edə bilirdi
**Səbəb:** `_get_owned_pending_transaction` ümumi (sender VƏ YA receiver) yoxlamasından istifadə edirdi. Yalnız SENDER-ə icazə verilməli idi.
**Fayl:** `backend/app/modules/transactions/service.py`

## 2. Changed Files
```
backend/app/core/config.py           + otp_delivery_channel (default: "email")
backend/app/core/logging.py          * JsonFormatter — bütün extra sahələri ötürür
backend/app/modules/transactions/service.py
  * initiate_transfer, confirm_transfer — konfiqurasiya edilən kanal + logging
  * _get_owned_pending_transaction — sender-only
  + resend_otp, _customer_is_sender
backend/app/modules/transactions/repository.py  + reissue
backend/app/modules/transactions/router.py      + POST /{id}/resend-otp
backend/app/modules/transactions/schemas.py     + ResendOtpResponse
.env.example                          + OTP_DELIVERY_CHANNEL sənədləşdirməsi
backend/tests/core/test_logging.py (yeni)
backend/tests/modules/transactions/test_transfer.py + 4 yeni test
frontend/src/services/transactionsService.ts, hooks/useTransactions.ts + resendOtp
frontend/src/components/modals/OtpConfirmModal.tsx + "Resend code" düyməsi
frontend/src/pages/customer/TransferPage.tsx * resend axını bağlandı
```

## 3. OTP Architecture (final)
```
Yalnız 1 OTP növü: TRANSFER (transaction_id-yə UNIQUE FK ilə bağlı)
Registration → OTP yoxdur
Login        → OTP yoxdur, könüllü TOTP
Transfer     → OTP var (initiate/resend/confirm, hash, 5 dəq expiry, max 5 cəhd, tək istifadəlik)
```

## 4. Email Flow
```
Frontend → POST /transactions/transfer → initiate_transfer
  → OTP_DELIVERY_CHANNEL=email (default) → send_notification_task.delay(..., "email", ...)
  → EMAIL_BACKEND=smtp isə real Gmail-ə çatır, console isə yalnız loglanır
```

## 5. Logging
Yeni event-lər: TRANSFER_OTP_CREATED, _SEND_REQUESTED, _RESENT, _VERIFIED, _INVALID, _EXPIRED, _MAX_ATTEMPTS_EXCEEDED, _VERIFY_FAILED. OTP kodunun özü heç vaxt loglanmır.

## 6-7. Security & Tests
226/226 backend test keçdi, mypy/ruff/tsc/eslint/build təmiz. Bax `VERIFICATION_REPORT.md` real canlı test nəticələri üçün.
