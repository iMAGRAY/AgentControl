"""Application service orchestrating documentation bridge operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agentcontrol.domain.docs import DocsBridgeConfig
from agentcontrol.domain.docs.aggregate import DocsBridgeAggregate, DocsBridgeContext
from agentcontrol.domain.docs.constants import remediation_for
from agentcontrol.domain.docs.value_objects import DocsBridgeConfigError
from agentcontrol.utils.docs_bridge import DEFAULT_CONFIG_RELATIVE

try:
    import jsonschema
except ImportError:  # pragma: no cover - guarded by dependency management
    jsonschema = None  # type: ignore[assignment]


@dataclass(frozen=True)
class DocsBridgeSchemaResult:
    """Outcome of validating docs.bridge.yaml against the JSON schema."""

    schema_id: str
    valid: bool
    errors: List[Dict[str, Any]]


class DocsBridgeServiceError(RuntimeError):
    """Raised when docs bridge operations cannot proceed."""

    def __init__(self, message: str, *, code: str, remediation: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.remediation = remediation if remediation is not None else remediation_for(code)


class DocsBridgeService:
    """High-level API for CLI interactions around the docs bridge."""

    SCHEMA_RESOURCE = "docs_bridge.schema.json"

    def __init__(self) -> None:
        self._schema_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def diagnose(self, project_path: Path) -> Dict[str, Any]:
        project_root = project_path.resolve()
        config_path = (project_root / DEFAULT_CONFIG_RELATIVE).resolve()
        raw_config = self._load_raw_config(config_path)
        schema_result = self._validate_against_schema(raw_config, config_path)

        try:
            config = self._build_config(raw_config, config_path)
        except DocsBridgeConfigError as exc:  # config invalid → return structured error
            return self._diagnostic_payload_for_config_error(project_root, config_path, exc, schema_result)

        context = DocsBridgeContext(project_root=project_root, config=config, config_path=config_path)
        aggregate = DocsBridgeAggregate(context)
        diagnosis = aggregate.diagnose()
        diagnosis["schema"] = {
            "id": self.schema_identifier,
            "valid": schema_result.valid,
            "errors": schema_result.errors,
            "path": str(self.schema_path()),
        }
        diagnosis["configExists"] = config_path.exists()
        return diagnosis

    def info(self, project_path: Path) -> Dict[str, Any]:
        project_root = project_path.resolve()
        config_path = (project_root / DEFAULT_CONFIG_RELATIVE).resolve()
        raw_config = self._load_raw_config(config_path)
        try:
            config = self._build_config(raw_config, config_path)
        except DocsBridgeConfigError as exc:
            raise DocsBridgeServiceError(exc.message, code=exc.code, remediation=exc.remediation) from exc

        context = DocsBridgeContext(project_root=project_root, config=config, config_path=config_path)
        aggregate = DocsBridgeAggregate(context)
        summary = aggregate.inspect(include_status=True)
        capabilities = self._capabilities_snapshot()
        return {
            "status": "ok",
            "config": summary,
            "configExists": config_path.exists(),
            "capabilities": capabilities,
            "schema": {
                "id": self.schema_identifier,
                "path": str(self.schema_path()),
            },
        }

    @property
    def schema_identifier(self) -> str:
        return f"agentcontrol://schemas/{self.SCHEMA_RESOURCE}"

    def schema_path(self) -> Path:
        resource = resources.files("agentcontrol.resources") / self.SCHEMA_RESOURCE
        return Path(resource)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _diagnostic_payload_for_config_error(
        self,
        project_root: Path,
        config_path: Path,
        error: DocsBridgeConfigError,
        schema_result: DocsBridgeSchemaResult,
    ) -> Dict[str, Any]:
        error_entry = {
            "code": error.code,
            "message": error.message,
            "path": [],
            "remediation": error.remediation,
        }
        schema_errors = schema_result.errors or [error_entry]
        return {
            "summary": {
                "configPath": str(config_path),
                "root": str(project_root),
                "rootExists": False,
                "sections": [],
            },
            "issues": [
                {
                    "severity": "error",
                    "code": error.code,
                    "message": error.message,
                    "section": None,
                    "remediation": error.remediation,
                }
            ],
            "status": "error",
            "schema": {
                "id": self.schema_identifier,
                "valid": False,
                "errors": schema_errors,
            },
            "configExists": config_path.exists(),
        }

    def _capabilities_snapshot(self) -> Dict[str, Any]:
        return {
            "managedRegions": True,
            "atomicWrites": True,
            "multiSectionPerFile": True,
            "anchorInsertion": True,
            "schemaValidation": jsonschema is not None,
        }

    def _load_raw_config(self, config_path: Path) -> Dict[str, Any]:
        if not config_path.exists():
            return {}
        try:
            return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - validation re-emits
            raise DocsBridgeServiceError(
                f"Invalid YAML in {config_path}: {exc}",
                code="DOC_BRIDGE_INVALID_CONFIG",
            ) from exc

    def _build_config(self, raw: Dict[str, Any], config_path: Path) -> DocsBridgeConfig:
        if not raw:
            return DocsBridgeConfig.default()
        return DocsBridgeConfig.from_dict(raw, config_path=config_path)

    def _validate_against_schema(
        self,
        raw: Dict[str, Any],
        config_path: Path,
    ) -> DocsBridgeSchemaResult:
        schema = self._load_schema()
        if jsonschema is None:
            return DocsBridgeSchemaResult(schema_id=self.schema_identifier, valid=True, errors=[])

        validator = jsonschema.Draft202012Validator(schema)  # type: ignore[attr-defined]
        errors: List[Dict[str, Any]] = []
        for error in sorted(validator.iter_errors(raw or {}), key=lambda e: e.path):
            errors.append(
                {
                    "code": "DOC_BRIDGE_SCHEMA_VIOLATION",
                    "message": error.message,
                    "path": list(error.path),
                    "remediation": remediation_for("DOC_BRIDGE_INVALID_CONFIG"),
                },
            )
        return DocsBridgeSchemaResult(
            schema_id=self.schema_identifier,
            valid=not errors,
            errors=errors,
        )

    def _load_schema(self) -> Dict[str, Any]:
        if self._schema_cache is not None:
            return self._schema_cache
        resource = resources.files("agentcontrol.resources") / self.SCHEMA_RESOURCE
        with resources.as_file(resource) as schema_path:
            schema_content = json.loads(schema_path.read_text(encoding="utf-8"))
        self._schema_cache = schema_content
        return schema_content
