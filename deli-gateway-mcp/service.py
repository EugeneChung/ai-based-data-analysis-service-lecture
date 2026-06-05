"""DataGatewayService — the validate -> build -> render -> execute path.

This is the heart of the gateway. For one tool call it:

    (1) validate   caller params against the tool's declared parameters
    (2) build      merge defaults/guardrails, compute date window + limit
    (3) render     fill the Jinja2 SQL template with the safe values
    (4) execute    run read-only + capped, and log the call

Every fixed tool shares this one path, so a guardrail added here applies
to all of them at once.
"""

from __future__ import annotations

import sys

import executor
from query_builder import build_context, render_sql
from validator import validate


class DataGatewayService:
    def __init__(self, tool_specs: dict, global_defaults: dict, global_guardrails: dict) -> None:
        self.tool_specs = tool_specs
        self.global_defaults = global_defaults
        self.global_guardrails = global_guardrails

    def execute_tool(self, tool_name: str, params: dict) -> dict:
        spec = self.tool_specs[tool_name]

        # (1) validate — caller input becomes SQL-safe values here
        clean = validate(spec, params or {})

        # (2) build — defaults, date window, row cap
        ctx = build_context(spec, self.global_defaults, self.global_guardrails, clean)

        # (3) render — fill the SQL template
        sql = render_sql(spec, ctx)

        # (4) execute — read-only + capped
        guardrails = {**self.global_guardrails, **spec.guardrails}
        result = executor.execute(
            sql,
            timeout_seconds=int(guardrails.get("timeout_seconds", 30)),
            limit=int(ctx["limit"]),
        )

        self._audit(tool_name, params, result)
        return {
            "tool": tool_name,
            "engine": spec.engine,
            "sql": sql,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }

    @staticmethod
    def _audit(tool_name: str, params: dict, result) -> None:
        # Stand-in for a real execution log (who ran what, how much it scanned).
        print(
            f"[gateway] tool={tool_name} params={params} "
            f"rows={result.row_count} truncated={result.truncated}",
            file=sys.stderr,
        )
