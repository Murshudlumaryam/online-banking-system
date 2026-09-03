"""
Fetches live exchange rates from Frankfurter (https://frankfurter.dev), a
free, no-API-key-needed rate service backed by the European Central Bank.

Deliberately lives inside app/modules/exchange_rates/ rather than a
generic app/services/ folder — every other domain in this codebase (auth,
transactions, cards, ...) keeps its external-integration code next to the
module it belongs to (see app/core/email.py's provider pattern for a
similar "one small client class, one job" shape). A parallel top-level
services/ directory would be a second, competing place to look for this
kind of code.

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

_FRANKFURTER_API_URL = "https://api.frankfurter.dev/v1/latest"


class ExchangeRateProviderError(Exception):
    """Raised when Frankfurter can't be reached or doesn't have a rate for
    the requested currency pair — the caller (see the admin router)
    translates this into a clean 4xx, never a raw 500."""


async def fetch_live_rate(*, source_currency: str, target_currency: str) -> float:
    source = source_currency.upper()
    target = target_currency.upper()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _FRANKFURTER_API_URL, params={"base": source, "symbols": target}
            )
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

    rates = payload.get("rates", {})
    if target not in rates:
        raise ExchangeRateProviderError(
            f"No rate available for {source} -> {target}"
        )
    return float(rates[target])
