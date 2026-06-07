"""Deli data-gateway — declarative, fixed-SQL MCP server (FastMCP).

The lecture-sized sibling of the internal teamdable/data-gateway-mcp.
Instead of letting the model write SQL (that is deli-db-mcp's job), this
server exposes a *catalog* of reviewed, parameterised queries as MCP
tools. Each catalog/<name>.yaml + queries/<name>.sql pair becomes one
tool whose parameters, defaults, and guardrails are fixed in the files.

One agent can use both connectors at once: deli-gateway for the
repeating, trusted questions; deli-db for free exploration.

Run (stdio):  python3 server.py
HTTP:         DELI_MCP_TRANSPORT=http python3 server.py   # default :8001
Register:     claude mcp add deli-gateway -- python3 /abs/path/to/server.py
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Optional

import yaml
from fastmcp import FastMCP

from catalog import CatalogLoader
from service import DataGatewayService

_HERE = Path(__file__).parent

# catalog parameter type -> python annotation used for the tool signature
_PY_TYPE = {"integer": int, "date": str, "string": str, "number": float}


def _make_handler(service: DataGatewayService, spec):
    """Build a tool function whose signature matches the catalog params,
    so FastMCP advertises the right typed arguments to the model.

    The body just forwards the non-empty arguments to the shared
    execute_tool pipeline; the per-tool difference lives entirely in the
    yaml + sql files, not in code.
    """

    def handler(**kwargs):
        params = {k: v for k, v in kwargs.items() if v is not None}
        payload = service.execute_tool(spec.name, params)
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    sig_params = []
    annotations: dict[str, object] = {}
    for p in spec.parameters:
        annot = Optional[_PY_TYPE.get(p.get("type", "string"), str)]
        annotations[p["name"]] = annot
        sig_params.append(
            inspect.Parameter(
                p["name"],
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=annot,
            )
        )
    annotations["return"] = str
    handler.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]
    handler.__annotations__ = annotations
    handler.__name__ = spec.name
    handler.__doc__ = spec.description
    return handler


def create_server(service: DataGatewayService, tool_specs: dict) -> FastMCP:
    mcp = FastMCP(name="deli-gateway")
    for name in sorted(tool_specs):
        spec = tool_specs[name]
        handler = _make_handler(service, spec)
        mcp.tool(name=spec.name, description=spec.description)(handler)
    return mcp


def build() -> FastMCP:
    config = yaml.safe_load((_HERE / "config.yaml").read_text(encoding="utf-8")) or {}
    tool_specs = CatalogLoader(_HERE / "catalog", _HERE / "queries").load()
    service = DataGatewayService(
        tool_specs,
        config.get("defaults", {}),
        config.get("guardrails", {}),
    )
    return create_server(service, tool_specs)


mcp = build()


if __name__ == "__main__":
    # stdio by default (Claude Desktop config-file route). Set
    # DELI_MCP_TRANSPORT=http to expose a URL for the "Add custom
    # connector" dialog: http://{host}:{port}{path} (default :8001 so it
    # sits next to deli-db-mcp on :8000).
    if os.environ.get("DELI_MCP_TRANSPORT") == "http":
        mcp.run(
            transport="http",
            host=os.environ.get("DELI_MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("DELI_MCP_PORT", "8001")),
            path=os.environ.get("DELI_MCP_PATH", "/mcp"),
        )
    else:
        mcp.run()
