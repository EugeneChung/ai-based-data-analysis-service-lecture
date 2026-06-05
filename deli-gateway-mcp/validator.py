"""Parameter validation — the trust boundary.

The SQL template fills {{ value }} straight into the query text, so a
raw caller value could otherwise break out of the statement. This module
is the ONE place that turns caller input into SQL-ready values:

    integer -> int(value)
    number  -> float(value)
    date    -> must match YYYY-MM-DD
    string  -> escaped with pymysql.escape_string

Anything missing, unknown, or malformed raises ValidationError and the
query is never built. Because every fixed tool goes through here, the
safety rule is written once and applied to all of them.
"""

from __future__ import annotations

import re

from pymysql.converters import escape_string

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationError(ValueError):
    pass


def validate(spec, params: dict) -> dict:
    declared = {p["name"]: p for p in spec.parameters}

    unknown = set(params) - set(declared)
    if unknown:
        raise ValidationError(f"unknown parameter(s): {', '.join(sorted(unknown))}")

    clean: dict[str, object] = {}
    for name, p in declared.items():
        if params.get(name) is None:
            if p.get("required"):
                raise ValidationError(f"missing required parameter: {name}")
            continue
        clean[name] = _coerce(name, p.get("type", "string"), params[name])
    return clean


def _coerce(name: str, type_: str, value):
    if type_ == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"parameter '{name}' must be an integer")
    if type_ == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"parameter '{name}' must be a number")
    if type_ == "date":
        text = str(value)
        if not _DATE_RE.match(text):
            raise ValidationError(f"parameter '{name}' must be a date (YYYY-MM-DD)")
        return text
    # string (and any text-like type): escape so a quote can't end the literal
    return escape_string(str(value))
