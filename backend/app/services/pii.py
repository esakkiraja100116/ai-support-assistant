"""Best-effort PII redaction for anything written to a local log file or sent
to an external observability service (OTel/Grafana Cloud).

This app's own data model has no phone/address/card columns today, so the
real exposure is free text a customer types into chat (which could contain
their own phone number, email, or card number) and, separately, structured
response payloads that shouldn't be logged in full regardless of content
(see `strip_sensitive_response_data`) - the tracking payload specifically.

Pattern-based redaction is inherently incomplete (it won't catch every
possible phone/ID format), so this is a defensive layer, not a guarantee -
the actual boundary is still "don't store more than you need to."
"""
import re
from typing import Any

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Requires a leading '+' (a country code) or a parenthesized area code -
# deliberately does NOT match a bare digit run, so AWB numbers
# ("PRO19460771"), order/transaction ids, and amounts are never touched.
_PHONE_RE = re.compile(
    r"(?<!\w)(\+\d{1,3}(?:[\s-]?\d{2,4}){2,5}|\(\d{2,4}\)[\s-]?\d{3,4}[\s-]?\d{3,4})(?!\w)"
)
# Standard grouped card format only (e.g. "4111 1111 1111 1111") - this
# grouping essentially never occurs in this app's own identifiers.
_CARD_RE = re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,4}\b")

# Structured response fields that must never be written to a log/trace in
# full, regardless of which response type carries them - the raw tracking
# payload and free-text failure reasons, per the "avoid logging the raw
# tracking payload by default" requirement.
_SENSITIVE_DATA_KEYS = {"history", "current_location", "latest_event", "failure_reason"}


def redact_text(text: str | None) -> str | None:
    """Scrubs common PII patterns from free text. Safe to call on None or
    empty strings (returns them unchanged)."""
    if not text:
        return text
    text = _CARD_RE.sub("[CARD]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    return text


def strip_sensitive_response_data(data: Any) -> Any:
    """Recursively replaces known-sensitive keys (the raw tracking payload's
    history/location, and free-text failure reasons) with a placeholder,
    leaving everything else (ids, statuses, amounts, types) intact - so
    session logs stay useful for debugging a flow without ever holding a
    full tracking history or a customer's card-decline free text."""
    if isinstance(data, dict):
        return {
            k: ("[REDACTED]" if k in _SENSITIVE_DATA_KEYS and v not in (None, [], "") else strip_sensitive_response_data(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [strip_sensitive_response_data(item) for item in data]
    return data
