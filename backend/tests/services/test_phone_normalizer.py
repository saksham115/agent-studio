"""Tests for ``phone_normalizer.normalize_phone``."""

from __future__ import annotations

import pytest

from app.services.phone_normalizer import normalize_phone


# ---------------------------------------------------------------------------
# Happy path: parses to E.164
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    # Indian numbers in IN region (default)
    ("9876543210", "+919876543210"),
    ("09876543210", "+919876543210"),
    ("+919876543210", "+919876543210"),
    # Already E.164 from another region — phonenumbers' canonical US example
    ("+12015550123", "+12015550123"),
    # Whitespace tolerance
    (" +919876543210 ", "+919876543210"),
    # Punctuation tolerance — phonenumbers strips it
    ("+91 (98765) 43210", "+919876543210"),
    ("+91-98765-43210", "+919876543210"),
])
def test_valid_numbers_return_e164(raw, expected):
    assert normalize_phone(raw) == expected


# ---------------------------------------------------------------------------
# None / empty / unparseable returns None — the dispatch signal for
# EndUserService to use the external_id column instead of phone_number.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [
    None,
    "",
    "   ",  # whitespace-only
    "sip:agentstudio@phone.plivo.com",  # SIP URI
    "user-12345",  # chatbot user_id
    "abc",
    "1",  # too short to be a valid phone in any region
    "not a phone",
])
def test_invalid_inputs_return_none(raw):
    assert normalize_phone(raw) is None


# ---------------------------------------------------------------------------
# Region override — same digits parse differently in different regions
# ---------------------------------------------------------------------------


def test_region_override_changes_parse():
    # The same 10-digit string is a valid US number but invalid in IN.
    # phonenumbers' US example: +12015550123 → "2015550123" without CC.
    raw = "2015550123"
    assert normalize_phone(raw, region="US") == "+12015550123"
    assert normalize_phone(raw, region="IN") is None
