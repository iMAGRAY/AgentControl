from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import pytest

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AESGCM = None

from agentcontrol.adapters.tasks.github_provider import GitHubIssuesProvider
from agentcontrol.adapters.tasks.jira_provider import JiraTaskProvider
from agentcontrol.ports.tasks.provider import TaskProviderError


class DummyResponse:
    def __init__(self, status_code: int, payload: Any, *, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class DummySession:
    def __init__(self, responses: list[DummyResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.auth: tuple[str, str] | None = None

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int | None = None) -> DummyResponse:
        self.calls.append((url, params))
        if not self._responses:
            raise AssertionError("no more responses queued")
        return self._responses.pop(0)


def _write_snapshot(tmp_path: Path, name: str, payload: Any) -> Path:
    snapshot = tmp_path / name
    snapshot.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def _write_encrypted_snapshot(tmp_path: Path, name: str, payload: Any, key: str) -> Path:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    key_bytes = key.encode("utf-8")
    cipher = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
    encoded = base64.b64encode(cipher).decode("ascii")
    snapshot = tmp_path / name
    snapshot.write_text(encoded, encoding="utf-8")
    return snapshot


def _write_aes_snapshot(tmp_path: Path, name: str, payload: Any, key: bytes) -> Path:
    if AESGCM is None:  # pragma: no cover - guarded by test skip
        raise RuntimeError('AESGCM unavailable')
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, data, None)
    encoded = base64.b64encode(nonce + ciphertext).decode("ascii")
    snapshot = tmp_path / name
    snapshot.write_text(encoded, encoding="utf-8")
    return snapshot


def test_jira_provider_snapshot(tmp_path: Path) -> None:
    payload = {
        "issues": [
            {
                "key": "AC-1",
                "fields": {
                    "summary": "Draft docs",
                    "status": {"name": "In Progress"},
                    "priority": {"name": "P1"},
                    "assignee": {"displayName": "Agent"},
                },
            }
        ]
    }
    snapshot = _write_snapshot(tmp_path, "jira.json", payload)
    provider = JiraTaskProvider({"snapshot_path": str(snapshot)})

    tasks = list(provider.fetch())
    assert tasks[0].id == "AC-1"
    assert tasks[0].status == "in progress"
    assert tasks[0].data["priority"] == "P1"
    assert tasks[0].data["owner"] == "Agent"


def test_jira_provider_encrypted_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "issues": [
            {
                "key": "AC-5",
                "fields": {
                    "summary": "Encrypted task",
                    "status": {"name": "To Do"},
                },
            }
        ]
    }
    key = "secret"
    snapshot = _write_encrypted_snapshot(tmp_path, "jira-enc.json", payload, key)
    monkeypatch.setenv("JIRA_SNAPSHOT_KEY", key)
    provider = JiraTaskProvider(
        {
            "snapshot_path": str(snapshot),
            "snapshot_encrypted": True,
            "snapshot_key_env": "JIRA_SNAPSHOT_KEY",
        }
    )

    tasks = list(provider.fetch())
    assert [task.id for task in tasks] == ["AC-5"]


def test_jira_provider_aes_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if AESGCM is None:
        pytest.skip('cryptography not available')
    payload = {
        "issues": [
            {
                "key": "AC-8",
                "fields": {
                    "summary": "AES encrypted",
                    "status": {"name": "In Progress"},
                },
            }
        ]
    }
    aes_key = AESGCM.generate_key(bit_length=256)
    snapshot = _write_aes_snapshot(tmp_path, "jira-aes.json", payload, aes_key)
    monkeypatch.setenv("JIRA_AES_KEY", base64.b64encode(aes_key).decode("utf-8"))
    provider = JiraTaskProvider(
        {
            "snapshot_path": str(snapshot),
            "snapshot_encryption": {"mode": "aes-256-gcm", "key_env": "JIRA_AES_KEY"},
        }
    )

    tasks = list(provider.fetch())
    assert [task.id for task in tasks] == ["AC-8"]


def test_jira_provider_api(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = DummyResponse(
        200,
        {
            "issues": [
                {
                    "key": "AC-2",
                    "fields": {
                        "summary": "Implement connector",
                        "status": {"name": "To Do"},
                    },
                }
            ],
            "total": 1,
        },
    )
    session = DummySession([page1])
    provider = JiraTaskProvider(
        {
            "base_url": "https://example.atlassian.net",
            "jql": "project = AC",
            "auth": {"email_env": "JIRA_EMAIL", "token_env": "JIRA_TOKEN"},
        },
        session=session,  # type: ignore[arg-type]
    )
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_TOKEN", "secret")

    tasks = list(provider.fetch())
    assert [task.id for task in tasks] == ["AC-2"]
    assert session.calls[0][0].endswith("/rest/api/3/search")


def test_github_provider_snapshot(tmp_path: Path) -> None:
    payload = {
        "issues": [
            {"number": 42, "title": "Improve docs", "state": "open"},
            {"number": 43, "title": "Closed", "state": "closed", "labels": ["triaged"]},
        ]
    }
    snapshot = _write_snapshot(tmp_path, "gh.json", payload)
    provider = GitHubIssuesProvider({"snapshot_path": str(snapshot)})

    tasks = {task.id: task for task in provider.fetch()}
    assert tasks["GITHUB-42"].status == "open"
    assert tasks["GITHUB-43"].status == "done"
    assert tasks["GITHUB-43"].data["labels"] == ["triaged"]


def test_github_provider_encrypted_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"issues": [{"number": 77, "title": "Encrypted", "state": "open"}]}
    key = "gh_key"
    snapshot = _write_encrypted_snapshot(tmp_path, "gh-enc.json", payload, key)
    monkeypatch.setenv("GH_SNAPSHOT_KEY", key)
    provider = GitHubIssuesProvider(
        {
            "snapshot_path": str(snapshot),
            "snapshot_encrypted": True,
            "snapshot_key_env": "GH_SNAPSHOT_KEY",
        }
    )

    tasks = list(provider.fetch())
    assert [task.id for task in tasks] == ["GITHUB-77"]


def test_github_provider_aes_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if AESGCM is None:
        pytest.skip('cryptography not available')
    payload = {"issues": [{"number": 90, "title": "AES", "state": "open"}]}
    aes_key = AESGCM.generate_key(bit_length=256)
    snapshot = _write_aes_snapshot(tmp_path, "gh-aes.json", payload, aes_key)
    monkeypatch.setenv("GH_AES_KEY", base64.b64encode(aes_key).decode("utf-8"))
    provider = GitHubIssuesProvider(
        {
            "snapshot_path": str(snapshot),
            "snapshot_encryption": {"mode": "aes-256-gcm", "key_env": "GH_AES_KEY"},
        }
    )

    tasks = list(provider.fetch())
    assert [task.id for task in tasks] == ["GITHUB-90"]


def test_github_provider_api(monkeypatch: pytest.MonkeyPatch) -> None:
    link_header = '<https://api.github.com/repos/org/repo/issues?page=2>; rel="next"'
    page1 = DummyResponse(
        200,
        [{"number": 1, "title": "Bug", "state": "open"}],
        headers={"Link": link_header},
    )
    page2 = DummyResponse(
        200,
        [{"number": 2, "title": "Fix", "state": "closed"}],
        headers={},
    )
    session = DummySession([page1, page2])
    provider = GitHubIssuesProvider(
        {
            "owner": "org",
            "repo": "repo",
            "token_env": "GITHUB_TOKEN",
        },
        session=session,  # type: ignore[arg-type]
    )
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    tasks = list(provider.fetch())
    assert [task.id for task in tasks] == ["GITHUB-1", "GITHUB-2"]


def test_github_provider_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GitHubIssuesProvider({"owner": "o", "repo": "r", "token_env": "MISSING"})
    with pytest.raises(TaskProviderError):
        provider.fetch()



def test_github_provider_encrypted_snapshot_missing_key(tmp_path: Path) -> None:
    payload = {"issues": [{"number": 33, "title": "Encrypted", "state": "open"}]}
    snapshot = _write_encrypted_snapshot(tmp_path, "gh-missing.json", payload, "miss")
    provider = GitHubIssuesProvider(
        {
            "snapshot_path": str(snapshot),
            "snapshot_encrypted": True,
            "snapshot_key_env": "GH_MISSING_KEY",
        }
    )
    with pytest.raises(TaskProviderError):
        list(provider.fetch())
