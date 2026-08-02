"""
Audit-driven tests for TransferMoneyRequest's amount validation boundaries —
negative, zero, too many decimal places, and the upper-bound ceiling added
during a production-readiness audit (see the comment on the field itself).
"""
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.transactions.schemas import TransferMoneyRequest


def _base_kwargs(**overrides):
    kwargs = {
        "sender_account_id": uuid.uuid4(),
        "receiver_account_number": "AZ00BANK12345678901234",
        "amount": Decimal("10.00"),
        "currency": "AZN",
    }
    kwargs.update(overrides)
    return kwargs


def test_zero_amount_is_rejected():
    with pytest.raises(ValidationError):
        TransferMoneyRequest(**_base_kwargs(amount=Decimal("0")))


def test_negative_amount_is_rejected():
    with pytest.raises(ValidationError):
        TransferMoneyRequest(**_base_kwargs(amount=Decimal("-10.00")))


def test_more_than_two_decimal_places_is_rejected():
    with pytest.raises(ValidationError):
        TransferMoneyRequest(**_base_kwargs(amount=Decimal("10.001")))


def test_two_decimal_places_is_accepted():
    request = TransferMoneyRequest(**_base_kwargs(amount=Decimal("10.99")))
    assert request.amount == Decimal("10.99")


def test_whole_number_amount_is_accepted():
    request = TransferMoneyRequest(**_base_kwargs(amount=Decimal("10")))
    assert request.amount == Decimal("10")


def test_amount_exceeding_the_numeric_column_capacity_is_rejected():
    """The amount/converted_amount DB columns are NUMERIC(18,2) — this
    ceiling exists so an absurd amount fails cleanly at the API boundary
    (422) instead of reaching the database and raising an unhandled numeric
    overflow error (safely caught as a generic 500 by the catch-all
    handler, but with no clear indication of what was actually wrong)."""
    with pytest.raises(ValidationError):
        TransferMoneyRequest(**_base_kwargs(amount=Decimal("99999999999999999999.00")))


def test_amount_at_the_ceiling_is_still_accepted():
    request = TransferMoneyRequest(**_base_kwargs(amount=Decimal("1000000000")))
    assert request.amount == Decimal("1000000000")


def test_amount_just_over_the_ceiling_is_rejected():
    with pytest.raises(ValidationError):
        TransferMoneyRequest(**_base_kwargs(amount=Decimal("1000000000.01")))
