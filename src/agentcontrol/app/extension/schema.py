"""Schema helpers for AgentControl extension manifests."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Iterable, Iterator, Tuple

from jsonschema import Draft202012Validator

_SCHEMA_RESOURCE = "extension_manifest.schema.json"
_SCHEMA_PACKAGE = "agentcontrol.resources"


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    resource = resources.files(_SCHEMA_PACKAGE) / _SCHEMA_RESOURCE
    with resource.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(_load_schema())


def iter_schema_errors(manifest: dict[str, Any]) -> Iterator[Tuple[str, str]]:
    """Yield (path, message) pairs for schema issues in the manifest."""
    validator = _validator()
    for error in validator.iter_errors(manifest):
        path = ".".join(str(item) for item in error.absolute_path)
        yield path, error.message


def validate_schema(manifest: dict[str, Any]) -> Iterable[Tuple[str, str]]:
    """Backwards compatible alias for iter_schema_errors."""
    return iter_schema_errors(manifest)


__all__ = ["iter_schema_errors", "validate_schema"]
