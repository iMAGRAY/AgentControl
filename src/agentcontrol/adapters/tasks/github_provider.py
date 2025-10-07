"""GitHub Issues task provider."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import requests

from agentcontrol.adapters.tasks.utils import read_snapshot
from agentcontrol.domain.tasks import TaskRecord, TaskRecordError
from agentcontrol.ports.tasks.provider import TaskProvider, TaskProviderError


@dataclass
class GitHubAuthConfig:
    token_env: str | None

    def resolve(self) -> str:
        if not self.token_env:
            raise TaskProviderError("github provider requires token_env for API usage")
        token = os.environ.get(self.token_env)
        if not token:
            raise TaskProviderError(
                f"github provider token missing in environment variable '{self.token_env}'"
            )
        return token


class GitHubIssuesProvider(TaskProvider):
    def __init__(self, options: Dict[str, Any], session: requests.Session | None = None) -> None:
        self._owner = options.get("owner")
        self._repo = options.get("repo")
        self._state = options.get("state", "open")
        labels = options.get("labels")
        if isinstance(labels, str):
            self._labels = [label.strip() for label in labels.split(",") if label.strip()]
        elif isinstance(labels, list):
            self._labels = [str(label).strip() for label in labels if str(label).strip()]
        else:
            self._labels = []
        snapshot = options.get("snapshot_path") or options.get("path")
        self._snapshot_path = str(snapshot) if snapshot else None

        encryption_opts = options.get("snapshot_encryption")
        if encryption_opts is not None and not isinstance(encryption_opts, dict):
            raise TaskProviderError("github provider snapshot_encryption must be object")
        if encryption_opts:
            mode = encryption_opts.get("mode", "xor")
            if not isinstance(mode, str) or not mode:
                raise TaskProviderError("github provider encryption.mode must be string")
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

        self._auth_config = GitHubAuthConfig(token_env=options.get("token_env"))
        self._session = session or requests.Session()

    def fetch(self) -> Iterable[TaskRecord]:
        if self._snapshot_path:
            return self._load_snapshot(self._snapshot_path)
        if not self._owner or not self._repo:
            raise TaskProviderError("github provider requires 'owner' and 'repo'")
        token = self._auth_config.resolve()
        return self._fetch_remote(token)

    def _load_snapshot(self, path: str) -> List[TaskRecord]:
        payload = read_snapshot(
            path,
            mode=self._snapshot_encryption_mode,
            key=self._snapshot_key,
            key_env=self._snapshot_key_env,
        )
        issues = payload.get("issues", payload)
        return self._normalise_issues(issues)

    def _fetch_remote(self, token: str) -> List[TaskRecord]:
        url = f"https://api.github.com/repos/{self._owner}/{self._repo}/issues"
        params = {"state": self._state}
        if self._labels:
            params["labels"] = ",".join(self._labels)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        }
        issues: List[dict[str, Any]] = []
        session = self._session
        while url:
            response = session.get(url, params=params, headers=headers, timeout=30)
            params = {}  # subsequent pages use link headers only
            if response.status_code >= 400:
                raise TaskProviderError(
                    f"github provider request failed: {response.status_code} {response.text}"
                )
            page_items = response.json()
            if isinstance(page_items, list):
                issues.extend(page_items)
            url = _next_link(response.headers.get("Link"))
        return self._normalise_issues(issues)

    def _normalise_issues(self, issues: Iterable[dict[str, Any]]) -> List[TaskRecord]:
        tasks: List[TaskRecord] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            if issue.get("pull_request"):
                # skip PRs
                continue
            number = issue.get("number") or issue.get("id")
            if number is None:
                continue
            title = issue.get("title", "")
            state = issue.get("state", "open")
            payload = {
                "title": title,
                "status": "done" if str(state).lower() == "closed" else "open",
            }
            labels = issue.get("labels")
            if isinstance(labels, list) and labels:
                payload["labels"] = [
                    label.get("name") if isinstance(label, dict) else str(label)
                    for label in labels
                ]
            task_id = f"GITHUB-{number}"
            try:
                tasks.append(TaskRecord(task_id, payload))
            except TaskRecordError as exc:
                raise TaskProviderError(str(exc)) from exc
        return tasks


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    parts = [part.strip() for part in link_header.split(",")]
    for part in parts:
        if "rel=\"next\"" in part:
            url_part, _ = part.split(";", 1)
            return url_part.strip(" <>")
    return None
