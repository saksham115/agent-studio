"""Phone-number normalization to E.164.

Used by ``EndUserService.get_or_create_by_caller`` to dispatch callers
between the ``end_users.phone_number`` index (parseable phones) and the
``end_users.external_id`` index (chatbot user_ids, SIP URIs, anything
else). The dispatch hinges on whether ``phonenumbers`` can parse the
raw caller identifier.

Returns ``None`` for empty input, parse failures, and inputs that aren't
valid phone numbers (e.g. SIP URIs, free-form chatbot session IDs).
"""

from __future__ import annotations

import phonenumbers


def normalize_phone(raw: str | None, region: str = "IN") -> str | None:
    """Return E.164 form of ``raw`` if it parses as a valid phone, else None.

    ``region`` is the default country code applied when the input has no
    explicit country code. ``"IN"`` means "+91" by default — Indian numbers
    written as ``9876543210`` parse to ``+919876543210``.
    """
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
