"""Jira task provider adapter."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import requests

from agentcontrol.adapters.tasks.utils import read_snapshot
from agentcontrol.domain.tasks import TaskRecord, TaskRecordError
from agentcontrol.ports.tasks.provider import TaskProvider, TaskProviderError

DEFAULT_FIELDS = ["summary", "status", "priority", "assignee"]


@dataclass
class JiraAuthConfig:
    email_env: str | None
    token_env: str | None

    def resolve(self) -> tuple[str, str]:
        email = os.environ.get(self.email_env or "") if self.email_env else None
        token = os.environ.get(self.token_env or "") if self.token_env else None
        if not email or not token:
            raise TaskProviderError(
                "jira provider requires non-empty credentials; set environment variables"
            )
        return email, token


class JiraTaskProvider(TaskProvider):
    def __init__(self, options: Dict[str, Any], session: requests.Session | None = None) -> None:
        self._base_url = options.get("base_url")
        self._jql = options.get("jql")
        snapshot = options.get("snapshot_path") or options.get("path")
        self._snapshot_path = str(snapshot) if snapshot else None

        encryption_opts = options.get("snapshot_encryption")
        if encryption_opts is not None and not isinstance(encryption_opts, dict):
            raise TaskProviderError("jira provider snapshot_encryption must be object")
        if encryption_opts:
            mode = encryption_opts.get("mode", "xor")
            if not isinstance(mode, str) or not mode:
                raise TaskProviderError("jira provider encryption.mode must be string")
            self._snapshot_encryption_mode = mode.lower()
            self._snapshot_key = encryption_opts.get("key")
            self._snapshot_key_env = encryption_opts.get("key_env")
        elif options.get("snapshot_encrypted"):
            self._snapshot_encryption_mode = "xor"
            self._snapshot_key = options.get("snapshot_key")
            self._snapshot_key_env = options.get("snapshot_key_env")
        else:
            self._snapshot_encryption_mode = None
            self._snapshot_key = None
            self._snapshot_key_env = None

        fields_option = options.get("fields")
        if fields_option:
            if isinstance(fields_option, str):
                fields = [field.strip() for field in fields_option.split(",") if field.strip()]
            else:
                fields = [str(field).strip() for field in fields_option if str(field).strip()]
            self._fields = fields or list(DEFAULT_FIELDS)
        else:
            self._fields = list(DEFAULT_FIELDS)
        self._max_results = int(options.get("max_results", 100))
        auth_opts = options.get("auth", {}) if isinstance(options.get("auth"), dict) else {}
        self._auth_config = JiraAuthConfig(
            email_env=auth_opts.get("email_env"),
            token_env=auth_opts.get("token_env"),
        )
        self._session = session or requests.Session()

    def fetch(self) -> Iterable[TaskRecord]:
        if self._snapshot_path:
            return self._load_snapshot(self._snapshot_path)
        if not self._base_url or not self._jql:
            raise TaskProviderError("jira provider requires 'base_url' and 'jql'")
        email, token = self._auth_config.resolve()
        return self._fetch_remote(email, token)

    def _load_snapshot(self, path: str) -> List[TaskRecord]:
        payload = read_snapshot(
            path,
            mode=self._snapshot_encryption_mode,
            key=self._snapshot_key,
            key_env=self._snapshot_key_env,
        )
        issues = payload.get("issues", payload)
        return self._normalise_issues(issues)

    def _fetch_remote(self, email: str, token: str) -> List[TaskRecord]:
        start_at = 0
        collected: List[TaskRecord] = []
        headers = {
            "Accept": "application/json",
        }
        self._session.auth = (email, token)
        while True:
            params = {
                "jql": self._jql,
                "fields": ",".join(self._fields),
                "maxResults": self._max_results,
                "startAt": start_at,
            }
            response = self._session.get(
                f"{self._base_url.rstrip('/')}/rest/api/3/search",
                params=params,
                headers=headers,
                timeout=30,
            )
            if response.status_code >= 400:
                raise TaskProviderError(
                    f"jira provider request failed: {response.status_code} {response.text}"
                )
            payload = response.json()
            issues = payload.get("issues", [])
            collected.extend(self._normalise_issues(issues))
            total = int(payload.get("total", len(collected)))
            start_at += self._max_results
            if start_at >= total or not issues:
                break
        return collected

    def _normalise_issues(self, issues: Iterable[dict[str, Any]]) -> List[TaskRecord]:
        tasks: List[TaskRecord] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            key = issue.get("key") or issue.get("id")
            fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
            title = fields.get("summary") or issue.get("title") or ""
            status = _jira_status(fields.get("status"))
            priority = _extract_value(fields.get("priority"))
            owner = _extract_value(fields.get("assignee"))
            payload = {
                "title": title,
                "status": status,
            }
            if priority:
                payload["priority"] = priority
            if owner:
                payload["owner"] = owner
            try:
                tasks.append(TaskRecord(str(key), payload))
            except TaskRecordError as exc:
                raise TaskProviderError(str(exc)) from exc
        return tasks


def _jira_status(status_field: Any) -> str:
    if isinstance(status_field, dict):
        return str(status_field.get("name", "open")).lower()
    if isinstance(status_field, str):
        return status_field.lower()
    return "open"


def _extract_value(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("displayName", "name", "value"):
            candidate = value.get(key)
            if candidate:
                return str(candidate)
    elif isinstance(value, str):
        return value
    return None
