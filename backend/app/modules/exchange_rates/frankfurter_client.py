"""
Fetches live exchange rates from Frankfurter (https://frankfurter.dev), a
free, no-API-key-needed rate service blending multiple central-bank and
official sources.

Deliberately lives inside app/modules/exchange_rates/ rather than a
generic app/services/ folder — every other domain in this codebase (auth,
transactions, cards, ...) keeps its external-integration code next to the
module it belongs to (see app/core/email.py's provider pattern for a
similar "one small client class, one job" shape). A parallel top-level
services/ directory would be a second, competing place to look for this
kind of code.

Uses Frankfurter's v2 API specifically, not v1: v1 only covers ~31
currencies from the ECB alone and does not include AZN (Azerbaijani
Manat) — confirmed against Frankfurter's own currency-request tracker
(github.com/lineofflight/frankfurter/issues/144), where AZN is listed as
requested-but-unsupported for v1. v2 blends multiple central-bank/official
sources and covers 201 currencies, AZN included (see
frankfurter.dev/currencies/azn/). v1's base/symbols query-string endpoint
and v2's /rate/{base}/{quote} path endpoint are different shapes; this
was found and fixed by actually hitting the endpoint with a real currency
pair from this project (AZN -> USD) and getting a live error, not by
reading the docs in isolation.

This client only *fetches* a rate for the admin to review — it never
writes to the database itself. Saving a fetched rate still goes through
the existing POST /admin/exchange-rates endpoint (see
app/modules/admin/router.py), same as a manually-typed rate. That keeps
"where a rate came from" out of scope for this client and avoids two
different code paths for the same database write.
"""
import logging

import httpx

logger = logging.getLogger("app.exchange_rates")

_FRANKFURTER_API_BASE = "https://api.frankfurter.dev/v2"


class ExchangeRateProviderError(Exception):
    """Raised when Frankfurter can't be reached or doesn't have a rate for
    the requested currency pair — the caller (see the admin router)
    translates this into a clean 4xx, never a raw 500."""


async def fetch_live_rate(*, source_currency: str, target_currency: str) -> float:
    source = source_currency.upper()
    target = target_currency.upper()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{_FRANKFURTER_API_BASE}/rate/{source}/{target}")
            # v2 uses 400/404/422 with a {"message": "..."} body for bad or
            # unsupported currency codes — raise_for_status surfaces all of
            # these as HTTPStatusError, which the except clause below turns
            # into the same clean ExchangeRateProviderError regardless of
            # which of the three it was.
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.warning(
            "exchange_rate_fetch_failed",
            extra={"source_currency": source, "target_currency": target},
        )
        raise ExchangeRateProviderError(
            f"Couldn't reach the exchange rate provider: {exc}"
        ) from exc

    if "rate" not in payload:
        raise ExchangeRateProviderError(f"No rate available for {source} -> {target}")
    return float(payload["rate"])
