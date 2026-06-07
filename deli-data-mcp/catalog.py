"""Catalog loader — turns declarative files into ToolSpecs.

Each fixed tool is described by two files that share a stem:

    catalog/<name>.yaml   parameters, defaults, guardrails, engine
    queries/<name>.sql    the parameterised SQL (a Jinja2 template)

CatalogLoader reads every catalog/*.yaml, pairs it with its .sql file,
and returns a {name: ToolSpec} dict that the server registers as MCP
tools. Adding a tool = adding one yaml + one sql file. No server code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ToolSpec:
    name: str
    description: str
    engine: str
    sql: str
    parameters: list[dict] = field(default_factory=list)
    defaults: dict = field(default_factory=dict)
    guardrails: dict = field(default_factory=dict)


class CatalogLoader:
    def __init__(self, catalog_dir: str | Path, queries_dir: str | Path) -> None:
        self.catalog_dir = Path(catalog_dir)
        self.queries_dir = Path(queries_dir)

    def load(self) -> dict[str, ToolSpec]:
        specs: dict[str, ToolSpec] = {}
        for yaml_path in sorted(self.catalog_dir.glob("*.yaml")):
            spec = self._load_one(yaml_path)
            specs[spec.name] = spec
        return specs

    def _load_one(self, yaml_path: Path) -> ToolSpec:
        meta = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        name = meta.get("name") or yaml_path.stem
        sql_path = self.queries_dir / f"{name}.sql"
        if not sql_path.exists():
            raise FileNotFoundError(
                f"catalog '{name}' has no matching query file: {sql_path}"
            )
        return ToolSpec(
            name=name,
            description=meta.get("description", ""),
            engine=meta.get("engine", "mysql"),
            sql=sql_path.read_text(encoding="utf-8"),
            parameters=meta.get("parameters", []),
            defaults=meta.get("defaults", {}),
            guardrails=meta.get("guardrails", {}),
        )
