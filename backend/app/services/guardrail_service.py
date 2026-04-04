"""Guardrail Service — enforce input/output guardrails with PII detection.

Provides compliance-critical checks against user input and agent output,
including detection and masking of Indian PII (Aadhaar, PAN, phone, email).
Every triggered rule is persisted to the ``guardrail_triggers`` audit table.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import GuardrailTrigger
from app.models.guardrail import Guardrail, GuardrailAction, GuardrailType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII regex patterns — Indian document numbers & general contact info
# ---------------------------------------------------------------------------

# Aadhaar: 12 digits, optionally separated by spaces into groups of 4.
# Uses word-boundary anchors and negative look-behind/ahead for digits to
# reduce false positives on arbitrary long numbers.
_AADHAAR_RE = re.compile(r"\b(\d{4})\s?(\d{4})\s?(\d{4})\b")

# PAN: Five uppercase letters, four digits, one uppercase letter.
_PAN_RE = re.compile(r"\b([A-Z]{5})(\d{4})([A-Z])\b")

# Indian phone numbers: optional country code (+91, 91, 0) followed by
# exactly 10 digits.  The pattern requires the 10-digit portion to start
# with 6-9 (valid Indian mobile prefixes) to reduce false positives.
_PHONE_RE = re.compile(r"\b(?:\+91[\s-]?|91[\s-]?|0)?([6-9]\d{9})\b")

# Email — intentionally broad; covers the vast majority of real-world
# addresses without trying to implement the full RFC 5322 grammar.
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Mapping from PII kind to (pattern, description)
_PII_PATTERNS: dict[str, tuple[re.Pattern, str]] = {
    "aadhaar": (_AADHAAR_RE, "Aadhaar number"),
    "pan": (_PAN_RE, "PAN card number"),
    "phone": (_PHONE_RE, "Phone number"),
    "email": (_EMAIL_RE, "Email address"),
}


# ---------------------------------------------------------------------------
# Result data-classes
# ---------------------------------------------------------------------------


@dataclass
class TriggeredRule:
    """A single guardrail that was triggered during evaluation."""

    guardrail_id: uuid.UUID
    name: str
    rule: str
    action: str  # block / warn / redirect / log
    details: str


@dataclass
class GuardrailResult:
    """Aggregate outcome of a guardrail check pass."""

    passed: bool
    triggered_rules: list[TriggeredRule] = field(default_factory=list)
    modified_text: str | None = None
    block_message: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GuardrailService:
    """Evaluate guardrails against user input or agent output.

    Usage::

        svc = GuardrailService(db)
        result = await svc.check_input(text, guardrails, conversation_id)
        if not result.passed:
            # block or warn
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -----------------------------------------------------------------------
    # Public — input checking
    # -----------------------------------------------------------------------

    async def check_input(
        self,
        text: str,
        guardrails: list[Guardrail],
        conversation_id: uuid.UUID | None = None,
    ) -> GuardrailResult:
        """Check *text* against INPUT, PII, and TOPIC guardrails.

        Returns a :class:`GuardrailResult` indicating whether the message
        should be allowed through.
        """
        if not text:
            return GuardrailResult(passed=True)

        # Filter to relevant, active guardrails sorted by descending priority
        # (higher priority = checked first).
        relevant_types = {GuardrailType.INPUT, GuardrailType.PII, GuardrailType.TOPIC}
        active = self._filter_active(guardrails, relevant_types)

        triggered: list[TriggeredRule] = []
        should_block = False
        block_message: str | None = None

        for guardrail in active:
            hits = self._evaluate_input_guardrail(guardrail, text)
            if not hits:
                continue

            for details in hits:
                rule = TriggeredRule(
                    guardrail_id=guardrail.id,
                    name=guardrail.name,
                    rule=guardrail.rule,
                    action=guardrail.action.value,
                    details=details,
                )
                triggered.append(rule)

                await self._log_trigger(
                    conversation_id=conversation_id,
                    guardrail=guardrail,
                    trigger_type=f"input_{guardrail.guardrail_type.value}",
                    details=details,
                    original_content=text,
                )

                if guardrail.action == GuardrailAction.BLOCK:
                    should_block = True
                    block_message = self._block_message(guardrail, details)

        return GuardrailResult(
            passed=not should_block,
            triggered_rules=triggered,
            block_message=block_message,
        )

    # -----------------------------------------------------------------------
    # Public — output checking
    # -----------------------------------------------------------------------

    async def check_output(
        self,
        text: str,
        guardrails: list[Guardrail],
        conversation_id: uuid.UUID | None = None,
    ) -> GuardrailResult:
        """Check *text* against OUTPUT, COMPLIANCE, and PII guardrails.

        If PII is detected in the output, the returned
        :attr:`GuardrailResult.modified_text` contains a redacted version.
        """
        if not text:
            return GuardrailResult(passed=True)

        relevant_types = {
            GuardrailType.OUTPUT,
            GuardrailType.COMPLIANCE,
            GuardrailType.PII,
        }
        active = self._filter_active(guardrails, relevant_types)

        triggered: list[TriggeredRule] = []
        should_block = False
        block_message: str | None = None
        modified_text: str = text

        for guardrail in active:
            if guardrail.guardrail_type == GuardrailType.PII:
                masked, pii_hits = self._mask_all_pii(modified_text)
                if pii_hits:
                    for pii_detail in pii_hits:
                        rule = TriggeredRule(
                            guardrail_id=guardrail.id,
                            name=guardrail.name,
                            rule=guardrail.rule,
                            action=guardrail.action.value,
                            details=pii_detail,
                        )
                        triggered.append(rule)

                        await self._log_trigger(
                            conversation_id=conversation_id,
                            guardrail=guardrail,
                            trigger_type="output_pii",
                            details=pii_detail,
                            original_content=text,
                            modified_content=masked,
                        )

                    modified_text = masked

            elif guardrail.guardrail_type == GuardrailType.COMPLIANCE:
                compliance_hits = self._check_compliance(guardrail, modified_text)
                for details in compliance_hits:
                    rule = TriggeredRule(
                        guardrail_id=guardrail.id,
                        name=guardrail.name,
                        rule=guardrail.rule,
                        action=guardrail.action.value,
                        details=details,
                    )
                    triggered.append(rule)

                    await self._log_trigger(
                        conversation_id=conversation_id,
                        guardrail=guardrail,
                        trigger_type="output_compliance",
                        details=details,
                        original_content=text,
                    )

                    if guardrail.action == GuardrailAction.BLOCK:
                        should_block = True
                        block_message = self._block_message(guardrail, details)

            elif guardrail.guardrail_type == GuardrailType.OUTPUT:
                output_hits = self._check_output_rules(guardrail, modified_text)
                for details in output_hits:
                    rule = TriggeredRule(
                        guardrail_id=guardrail.id,
                        name=guardrail.name,
                        rule=guardrail.rule,
                        action=guardrail.action.value,
                        details=details,
                    )
                    triggered.append(rule)

                    await self._log_trigger(
                        conversation_id=conversation_id,
                        guardrail=guardrail,
                        trigger_type="output_rule",
                        details=details,
                        original_content=text,
                    )

                    if guardrail.action == GuardrailAction.BLOCK:
                        should_block = True
                        block_message = self._block_message(guardrail, details)

        text_was_modified = modified_text != text

        return GuardrailResult(
            passed=not should_block,
            triggered_rules=triggered,
            modified_text=modified_text if text_was_modified else None,
            block_message=block_message,
        )

    # -----------------------------------------------------------------------
    # Audit logging
    # -----------------------------------------------------------------------

    async def _log_trigger(
        self,
        conversation_id: uuid.UUID | None,
        guardrail: Guardrail,
        trigger_type: str,
        details: str,
        original_content: str | None = None,
        modified_content: str | None = None,
    ) -> None:
        """Persist a :class:`GuardrailTrigger` audit row.

        If *conversation_id* is ``None`` (e.g. during dry-run / preview
        evaluation), the trigger is **not** persisted but is still logged.
        """
        logger.info(
            "Guardrail triggered: name=%s type=%s action=%s details=%s",
            guardrail.name,
            trigger_type,
            guardrail.action.value,
            details,
        )

        if conversation_id is None:
            return

        try:
            trigger = GuardrailTrigger(
                conversation_id=conversation_id,
                guardrail_id=guardrail.id,
                guardrail_name=guardrail.name,
                triggered_rule=guardrail.rule,
                action_taken=guardrail.action.value,
                original_content=original_content,
                modified_content=modified_content,
            )
            self.db.add(trigger)
            await self.db.flush()
        except Exception:
            logger.exception("Failed to persist GuardrailTrigger audit record")

    # -----------------------------------------------------------------------
    # Input evaluation helpers
    # -----------------------------------------------------------------------

    def _evaluate_input_guardrail(
        self, guardrail: Guardrail, text: str
    ) -> list[str]:
        """Return a list of detail strings for every violation found.

        Empty list means no violation.
        """
        if guardrail.guardrail_type == GuardrailType.PII:
            return self._detect_pii(text)
        elif guardrail.guardrail_type == GuardrailType.TOPIC:
            return self._check_topic(guardrail, text)
        elif guardrail.guardrail_type == GuardrailType.INPUT:
            return self._check_input_rule(guardrail, text)
        return []

    def _detect_pii(self, text: str) -> list[str]:
        """Detect all PII occurrences in *text* and return detail strings."""
        hits: list[str] = []

        for kind, (pattern, label) in _PII_PATTERNS.items():
            for match in pattern.finditer(text):
                hits.append(f"{label} detected: {self._redact_match(kind, match)}")

        return hits

    def _check_topic(self, guardrail: Guardrail, text: str) -> list[str]:
        """Check whether *text* contains banned topics/keywords.

        The guardrail ``rule`` is expected to contain a comma-separated list
        of banned keywords or phrases.  Matching is case-insensitive.
        """
        keywords = self._parse_keywords(guardrail.rule)
        if not keywords:
            return []

        text_lower = text.lower()
        hits: list[str] = []
        for keyword in keywords:
            if keyword in text_lower:
                hits.append(f"Banned topic detected: '{keyword}'")

        return hits

    def _check_input_rule(self, guardrail: Guardrail, text: str) -> list[str]:
        """Apply generic INPUT guardrail rules (keyword-based for MVP).

        Rule format: comma-separated keywords that must NOT appear in the
        input.  If any are found the rule triggers.
        """
        keywords = self._parse_keywords(guardrail.rule)
        if not keywords:
            return []

        text_lower = text.lower()
        hits: list[str] = []
        for keyword in keywords:
            if keyword in text_lower:
                hits.append(f"Input rule violation: '{keyword}' found")

        return hits

    # -----------------------------------------------------------------------
    # Output evaluation helpers
    # -----------------------------------------------------------------------

    def _check_compliance(self, guardrail: Guardrail, text: str) -> list[str]:
        """Check compliance rules against agent output.

        Rule format — one of two conventions:

        1. **must_mention:<keywords>** — the output *must* include at least
           one of the listed keywords (comma-separated).  E.g.
           ``must_mention:free-look period,cancellation rights``

        2. **must_not_mention:<keywords>** — the output must *not* include
           any of the listed keywords.

        3. Plain comma-separated keywords — treated as *must_not_mention*.
        """
        rule = guardrail.rule.strip()
        text_lower = text.lower()
        hits: list[str] = []

        if rule.lower().startswith("must_mention:"):
            required = self._parse_keywords(rule.split(":", 1)[1])
            if required and not any(kw in text_lower for kw in required):
                hits.append(
                    f"Compliance violation: output must mention one of "
                    f"[{', '.join(required)}]"
                )
        elif rule.lower().startswith("must_not_mention:"):
            banned = self._parse_keywords(rule.split(":", 1)[1])
            for kw in banned:
                if kw in text_lower:
                    hits.append(
                        f"Compliance violation: output must not mention '{kw}'"
                    )
        else:
            # Default: treat as must_not_mention
            banned = self._parse_keywords(rule)
            for kw in banned:
                if kw in text_lower:
                    hits.append(
                        f"Compliance violation: banned term '{kw}' found in output"
                    )

        return hits

    def _check_output_rules(self, guardrail: Guardrail, text: str) -> list[str]:
        """Apply generic OUTPUT guardrail rules.

        Supported rule prefixes:

        * ``max_length:<n>`` — output must not exceed *n* characters.
        * ``banned_words:<words>`` — comma-separated words that must not
          appear in the output.
        * Plain comma-separated keywords — treated as banned words.
        """
        rule = guardrail.rule.strip()
        text_lower = text.lower()
        hits: list[str] = []

        if rule.lower().startswith("max_length:"):
            try:
                max_len = int(rule.split(":", 1)[1].strip())
                if len(text) > max_len:
                    hits.append(
                        f"Output exceeds max length: {len(text)} > {max_len}"
                    )
            except ValueError:
                logger.warning(
                    "Invalid max_length rule value in guardrail '%s'",
                    guardrail.name,
                )
        elif rule.lower().startswith("banned_words:"):
            banned = self._parse_keywords(rule.split(":", 1)[1])
            for word in banned:
                if word in text_lower:
                    hits.append(f"Banned word found in output: '{word}'")
        else:
            banned = self._parse_keywords(rule)
            for word in banned:
                if word in text_lower:
                    hits.append(f"Output rule violation: '{word}' found")

        return hits

    # -----------------------------------------------------------------------
    # PII masking — output
    # -----------------------------------------------------------------------

    def _mask_all_pii(self, text: str) -> tuple[str, list[str]]:
        """Mask every PII occurrence in *text*.

        Returns ``(masked_text, list_of_detail_strings)``.
        """
        details: list[str] = []
        masked = text

        # Order matters: mask longer patterns first to avoid partial
        # re-matching.  Aadhaar first (12 digits), then PAN, phone, email.
        masked, aadhaar_hits = self._mask_aadhaar(masked)
        details.extend(aadhaar_hits)

        masked, pan_hits = self._mask_pan(masked)
        details.extend(pan_hits)

        masked, phone_hits = self._mask_phone(masked)
        details.extend(phone_hits)

        masked, email_hits = self._mask_email(masked)
        details.extend(email_hits)

        return masked, details

    def _mask_aadhaar(self, text: str) -> tuple[str, list[str]]:
        """Replace Aadhaar numbers, keeping only the last 4 digits.

        ``1234 5678 9012`` -> ``XXXX XXXX 9012``
        """
        hits: list[str] = []

        def _replacer(m: re.Match) -> str:
            last4 = m.group(3)
            hits.append(f"Aadhaar number masked (last 4: {last4})")
            # Preserve the spacing style of the original match
            full = m.group(0)
            if " " in full:
                return f"XXXX XXXX {last4}"
            return f"XXXXXXXX{last4}"

        masked = _AADHAAR_RE.sub(_replacer, text)
        return masked, hits

    def _mask_pan(self, text: str) -> tuple[str, list[str]]:
        """Replace PAN numbers, keeping the middle 4 digits.

        ``ABCDE1234F`` -> ``XXXXX1234X``
        """
        hits: list[str] = []

        def _replacer(m: re.Match) -> str:
            digits = m.group(2)
            hits.append(f"PAN number masked (digits: {digits})")
            return f"XXXXX{digits}X"

        masked = _PAN_RE.sub(_replacer, text)
        return masked, hits

    def _mask_phone(self, text: str) -> tuple[str, list[str]]:
        """Replace phone numbers with ``[REDACTED PHONE]``."""
        hits: list[str] = []

        def _replacer(m: re.Match) -> str:
            hits.append("Phone number masked")
            return "[REDACTED PHONE]"

        masked = _PHONE_RE.sub(_replacer, text)
        return masked, hits

    def _mask_email(self, text: str) -> tuple[str, list[str]]:
        """Replace email addresses with ``[REDACTED EMAIL]``."""
        hits: list[str] = []

        def _replacer(m: re.Match) -> str:
            hits.append("Email address masked")
            return "[REDACTED EMAIL]"

        masked = _EMAIL_RE.sub(_replacer, text)
        return masked, hits

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _filter_active(
        guardrails: list[Guardrail],
        types: set[GuardrailType],
    ) -> list[Guardrail]:
        """Return active guardrails of the given types, sorted by priority descending."""
        return sorted(
            (
                g
                for g in guardrails
                if g.is_active and g.guardrail_type in types
            ),
            key=lambda g: g.priority,
            reverse=True,
        )

    @staticmethod
    def _parse_keywords(rule_text: str) -> list[str]:
        """Split a comma-separated rule into lowercased, stripped keywords.

        Blank entries are discarded.
        """
        return [kw.strip().lower() for kw in rule_text.split(",") if kw.strip()]

    @staticmethod
    def _block_message(guardrail: Guardrail, details: str) -> str:
        """Build a user-facing block message from *guardrail* config or a default."""
        config = guardrail.action_config or {}
        custom_msg = config.get("block_message")
        if custom_msg:
            return custom_msg
        return (
            f"Your message was blocked by policy '{guardrail.name}': {details}"
        )

    @staticmethod
    def _redact_match(kind: str, match: re.Match) -> str:
        """Return a safely redacted representation of a PII match for logging."""
        raw = match.group(0)
        if kind == "aadhaar":
            return f"XXXX XXXX {raw[-4:]}"
        elif kind == "pan":
            # Show only the structure: XXXXX####X
            return f"XXXXX{raw[5:9]}X"
        elif kind == "phone":
            return f"XXXXXX{raw[-4:]}"
        elif kind == "email":
            at_idx = raw.find("@")
            if at_idx > 2:
                return f"{raw[:2]}***@{raw[at_idx + 1:]}"
            return "[REDACTED EMAIL]"
        return "[REDACTED]"
