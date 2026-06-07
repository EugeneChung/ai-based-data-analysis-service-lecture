"""Query builder — merges defaults/guardrails, then renders the SQL.

Given a validated parameter dict, this:
  1. fills a default date window when the tool declares date params but
     the caller omitted them (defaults.date_range_days),
  2. caps the row limit at the tool's guardrail (guardrails.max_rows),
  3. renders the Jinja2 SQL template with the final context.

Values are already type-checked by validator.validate, so the render
step here is safe.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from jinja2 import Environment

_env = Environment(autoescape=False)


def build_context(spec, global_defaults: dict, global_guardrails: dict, params: dict) -> dict:
    defaults = {**global_defaults, **spec.defaults}
    guardrails = {**global_guardrails, **spec.guardrails}

    ctx: dict[str, Any] = dict(params)

    declared = {p["name"] for p in spec.parameters}
    if {"date_from", "date_to"} & declared:
        _fill_date_window(ctx, defaults)

    max_rows = int(guardrails.get("max_rows", 1000))
    requested = ctx.get("limit", defaults.get("limit", max_rows))
    ctx["limit"] = max(1, min(int(requested), max_rows))
    return ctx


def _fill_date_window(ctx: dict, defaults: dict) -> None:
    window = int(defaults.get("date_range_days", 7))
    if not ctx.get("date_to"):
        ctx["date_to"] = date.today().isoformat()
    if not ctx.get("date_from"):
        end = date.fromisoformat(str(ctx["date_to"]))
        ctx["date_from"] = (end - timedelta(days=window - 1)).isoformat()


def render_sql(spec, ctx: dict) -> str:
    return _env.from_string(spec.sql).render(**ctx).strip()
