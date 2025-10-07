from __future__ import annotations

import json
import os
import base64
from pathlib import Path
from typing import Any

import pytest

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AESGCM = None

from agentcontrol.app.tasks import TaskSyncError, TaskSyncService
from agentcontrol.app.mission.service import MissionService
from agentcontrol.domain.project import ProjectId
from agentcontrol.domain.tasks import TaskBoard


def _prepare_project(root: Path) -> tuple[Path, Path]:
    board_path = root / "data" / "tasks.board.json"
    board_path.parent.mkdir(parents=True, exist_ok=True)
    board_payload = {
        "version": "0.1.0",
        "updated_at": "2025-10-01T00:00:00Z",
        "tasks": [
            {
                "id": "T1",
                "title": "Existing feature",
                "status": "open",
                "priority": "P1",
                "owner": "core",
            },
            {
                "id": "T3",
                "title": "To be archived",
                "status": "open",
                "priority": "P3",
                "owner": "core",
            },
        ],
    }
    board_path.write_text(json.dumps(board_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    provider_dir = root / "state" / "provider"
    provider_dir.mkdir(parents=True, exist_ok=True)
    provider_path = provider_dir / "tasks_snapshot.json"
    provider_payload = {
        "tasks": [
            {
                "id": "T1",
                "title": "Existing feature",
                "status": "done",
                "priority": "P1",
            },
            {
                "id": "T2",
                "title": "New automation",
                "status": "open",
                "priority": "P1",
            },
        ]
    }
    provider_path.write_text(json.dumps(provider_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    config_path = root / "config" / "tasks.provider.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_payload = {
        "type": "file",
        "options": {"path": str(provider_path.relative_to(root))},
    }
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return board_path, config_path


def test_task_sync_service_dry_run(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    board_path, config_path = _prepare_project(project_root)
    service = TaskSyncService(ProjectId.for_new_project(project_root))

    result = service.sync(config_path=config_path, apply=False)

    assert result.applied is False
    summary = result.plan.summary()
    assert summary == {"total": 3, "create": 1, "update": 1, "close": 1, "unchanged": 0}
    assert result.report_path.exists()
    report_payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report_payload["applied"] is False
    assert report_payload["summary"] == summary
    assert TaskBoard.load(board_path).tasks["T1"].status == "open"


def test_task_sync_service_apply(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    board_path, config_path = _prepare_project(project_root)
    service = TaskSyncService(ProjectId.for_new_project(project_root))

    result = service.sync(config_path=config_path, apply=True)
    assert result.applied is True
    board = TaskBoard.load(board_path)
    assert board.tasks["T1"].status == "done"
    assert "T2" in board.tasks
    assert board.tasks["T3"].status == "done"

    latest_summary = json.loads((project_root / "reports" / "tasks" / "sync.json").read_text(encoding="utf-8"))
    assert latest_summary["summary"]["create"] == 1
    history_dir = project_root / "reports" / "tasks" / "history"
    history_files = list(history_dir.glob("*.json"))
    assert history_files


def test_task_sync_service_mission_summary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _, config_path = _prepare_project(project_root)
    service = TaskSyncService(ProjectId.for_new_project(project_root))
    service.sync(config_path=config_path, apply=True)

    mission = MissionService()
    summary = mission._task_board(project_root)  # type: ignore[attr-defined]
    assert summary["counts"]["total"] == 3
    assert summary["counts"]["open"] == 1
    assert summary["counts"]["done"] == 2
    assert summary["lastSync"]["summary"]["create"] == 1


def test_task_sync_service_missing_config(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    service = TaskSyncService(ProjectId.for_new_project(project_root))

    with pytest.raises(TaskSyncError):
        service.sync(config_path=project_root / "config" / "missing.json")


def test_task_sync_service_jira_snapshot(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    board_path, _ = _prepare_project(project_root)

    jira_snapshot = project_root / "state" / "provider" / "jira.json"
    jira_snapshot.parent.mkdir(parents=True, exist_ok=True)
    jira_snapshot.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "key": "T1",
                        "fields": {
                            "summary": "Existing feature",
                            "status": {"name": "Done"},
                        },
                    },
                    {
                        "key": "T4",
                        "fields": {
                            "summary": "New issue",
                            "status": {"name": "In Progress"},
                        },
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    config_path = project_root / "config" / "tasks.provider.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "type": "jira",
                "options": {"snapshot_path": str(jira_snapshot.relative_to(project_root))},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = TaskSyncService(ProjectId.for_new_project(project_root))
    result = service.sync(config_path=config_path, apply=True)
    assert result.applied is True
    board = TaskBoard.load(board_path)
    assert board.tasks["T1"].status == "done"
    assert board.tasks["T4"].status == "in progress"

def _xor_encrypt(payload: dict[str, Any], key: str) -> str:
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    key_bytes = key.encode("utf-8")
    encrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw))
    return base64.b64encode(encrypted).decode("utf-8")


def _aes_encrypt(payload: dict[str, Any], key: bytes, nonce: bytes | None = None) -> str:
    if AESGCM is None:  # pragma: no cover - guarded by test skip
        raise RuntimeError('AESGCM unavailable')
    nonce = nonce or os.urandom(12)
    aesgcm = AESGCM(key)
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, raw, None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')


def test_task_sync_service_encrypted_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    board_path, _ = _prepare_project(project_root)

    snapshot_payload = {
        "tasks": [
            {"id": "T1", "title": "Existing feature", "status": "done"},
            {"id": "T5", "title": "Encrypted import", "status": "open"},
        ]
    }
    key = "s3cret"
    snapshot = project_root / "state" / "provider" / "encrypted.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(_xor_encrypt(snapshot_payload, key), encoding="utf-8")

    config_path = project_root / "config" / "tasks.provider.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "type": "file",
                "options": {
                    "path": str(snapshot.relative_to(project_root)),
                    "encryption": {"mode": "xor", "key_env": "TASKS_KEY"},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("TASKS_KEY", key)
    service = TaskSyncService(ProjectId.for_new_project(project_root))

    result = service.sync(config_path=config_path, apply=True)

    board = TaskBoard.load(board_path)
    assert board.tasks["T1"].status == "done"
    assert "T5" in board.tasks
    encryption_opts = result.provider_config["options"]["encryption"]
    assert encryption_opts["mode"] == "xor"
    assert encryption_opts["key_env"] == "TASKS_KEY"
    assert encryption_opts.get("key") in (None, '***')


def test_task_sync_service_aes_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if AESGCM is None:
        pytest.skip('cryptography not available')
    project_root = tmp_path / "project"
    project_root.mkdir()
    board_path, _ = _prepare_project(project_root)

    aes_key = AESGCM.generate_key(bit_length=256)
    payload = {
        "tasks": [
            {"id": "T1", "title": "Existing feature", "status": "done"},
            {"id": "T6", "title": "AES import", "status": "open"},
        ]
    }
    snapshot = project_root / "state" / "provider" / "tasks_aes.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(_aes_encrypt(payload, aes_key), encoding="utf-8")

    key_env_value = base64.b64encode(aes_key).decode("utf-8")
    monkeypatch.setenv("TASKS_AES_KEY", key_env_value)

    config_path = project_root / "config" / "tasks.provider.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "type": "file",
                "options": {
                    "path": str(snapshot.relative_to(project_root)),
                    "encryption": {"mode": "aes-256-gcm", "key_env": "TASKS_AES_KEY"},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = TaskSyncService(ProjectId.for_new_project(project_root))
    result = service.sync(config_path=config_path, apply=True)

    board = TaskBoard.load(board_path)
    assert board.tasks["T1"].status == "done"
    assert "T6" in board.tasks
    encryption_opts = result.provider_config["options"]["encryption"]
    assert encryption_opts["mode"] == "aes-256-gcm"
    assert encryption_opts["key_env"] == "TASKS_AES_KEY"


def test_task_sync_service_encryption_missing_key(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (_, config_path) = _prepare_project(project_root)
    # overwrite config with encrypted snapshot lacking key/key_env
    config_payload = {
        "type": "file",
        "options": {
            "path": "state/provider/tasks_snapshot.json",
            "encrypted": True
        },
    }
    config_path = project_root / "config" / "tasks.provider.json"
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    service = TaskSyncService(ProjectId.for_new_project(project_root))
    with pytest.raises(TaskSyncError):
        service.sync(config_path=config_path, apply=False)


def test_task_sync_service_encryption_empty_key(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (_, config_path) = _prepare_project(project_root)
    config_payload = {
        "type": "file",
        "options": {
            "path": "state/provider/tasks_snapshot.json",
            "encrypted": True,
            "key": ""
        },
    }
    config_path = project_root / "config" / "tasks.provider.json"
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    service = TaskSyncService(ProjectId.for_new_project(project_root))
    with pytest.raises(TaskSyncError):
        service.sync(config_path=config_path, apply=False)


def test_task_sync_service_inline_provider(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    project_root.mkdir()
    board_path, _ = _prepare_project(project_root)
    provider_path = project_root / 'state' / 'provider' / 'tasks_snapshot.json'

    service = TaskSyncService(ProjectId.for_new_project(project_root))
    result = service.sync(
        provider={'type': 'file', 'options': {'path': str(provider_path.relative_to(project_root))}}
    )

    assert result.applied is False
    assert result.plan.summary() == {'total': 3, 'create': 1, 'update': 1, 'close': 1, 'unchanged': 0}
    assert result.provider_config['type'] == 'file'
    board = TaskBoard.load(board_path)
    assert board.tasks['T1'].status == 'open'

