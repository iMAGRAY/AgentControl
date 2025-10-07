from __future__ import annotations

import json
import base64
import os
from pathlib import Path
from typing import Any

import pytest

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AESGCM = None

from agentcontrol.cli import main as cli_main
from agentcontrol.cli.main import _build_services


def _setup_project(tmp_path: Path) -> Path:
    bootstrap, _ = _build_services()
    project_root = tmp_path / "project"
    project_root.mkdir()
    cli_main._auto_bootstrap_project(bootstrap, project_root, "tasks")
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    board_path = data_dir / "tasks.board.json"
    board_path.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "updated_at": "2025-10-01T00:00:00Z",
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Existing",
                        "status": "open",
                        "priority": "P1",
                    },
                    {
                        "id": "TASK-2",
                        "title": "Stale",
                        "status": "open",
                        "priority": "P2",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root


def _write_remote(tmp_path: Path) -> Path:
    remote_path = tmp_path / "remote.json"
    remote_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Existing",
                        "status": "in_progress",
                        "priority": "P1",
                    },
                    {
                        "id": "TASK-3",
                        "title": "New Task",
                        "status": "open",
                        "priority": "P0",
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return remote_path


def _write_aes_snapshot(base_dir: Path, name: str, payload: dict[str, Any], key: bytes) -> Path:
    if AESGCM is None:  # pragma: no cover - guarded by test skip
        raise RuntimeError('AESGCM unavailable')
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, raw, None)
    snapshot_path = base_dir / name
    snapshot_path.write_text(base64.b64encode(nonce + ciphertext).decode('utf-8'), encoding='utf-8')
    return snapshot_path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return _setup_project(tmp_path)


def test_tasks_sync_dry_run(project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    remote = _write_remote(tmp_path)
    provider_dir = project / 'state' / 'provider'
    provider_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = provider_dir / 'tasks_snapshot.json'
    snapshot_path.write_text(remote.read_text(encoding='utf-8'), encoding='utf-8')
    config_dir = project / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / 'tasks.provider.json'
    config_payload = {
        'type': 'file',
        'options': {
            'path': str(snapshot_path.relative_to(project)),
        },
    }
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')

    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--json',
    ])
    assert exit_code == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report['applied'] is False
    summary = report['summary']
    assert summary == {'total': 3, 'create': 1, 'update': 1, 'close': 1, 'unchanged': 0}
    kinds = {action['op'] for action in report['actions']}
    assert kinds == {'create', 'update', 'close'}
    board = json.loads((project / 'data' / 'tasks.board.json').read_text(encoding='utf-8'))
    assert board['tasks'][0]['status'] == 'open'



def test_tasks_sync_apply(project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    remote = _write_remote(tmp_path)
    provider_dir = project / 'state' / 'provider'
    provider_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = provider_dir / 'tasks_snapshot.json'
    snapshot_path.write_text(remote.read_text(encoding='utf-8'), encoding='utf-8')
    config_dir = project / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / 'tasks.provider.json'
    config_payload = {
        'type': 'file',
        'options': {
            'path': str(snapshot_path.relative_to(project)),
        },
    }
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')

    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--apply',
    ])
    assert exit_code == 0
    board_path = project / 'data' / 'tasks.board.json'
    board = json.loads(board_path.read_text(encoding='utf-8'))
    tasks = {task['id']: task for task in board['tasks']}
    assert tasks['TASK-1']['status'] == 'in_progress'
    assert tasks['TASK-3']['status'] == 'open'
    assert tasks['TASK-2']['status'] == 'done'
    report_path = project / 'reports' / 'tasks' / 'sync.json'
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding='utf-8'))
    assert payload['applied'] is True
    assert payload['summary'] == {'total': 3, 'create': 1, 'update': 1, 'close': 1, 'unchanged': 0}



def test_tasks_sync_cli_snapshot_encryption(
    project: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if AESGCM is None:
        pytest.skip('cryptography not available')

    payload = {
        'issues': [
            {
                'key': 'AC-99',
                'fields': {
                    'summary': 'AES snapshot',
                    'status': {'name': 'To Do'},
                },
            }
        ]
    }
    aes_key = AESGCM.generate_key(bit_length=256)
    provider_dir = project / 'state' / 'provider'
    provider_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = _write_aes_snapshot(provider_dir, 'jira_aes.json', payload, aes_key)

    config_dir = project / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / 'tasks.provider.json'
    config_payload = {
        'type': 'jira',
        'options': {
            'snapshot_path': str(snapshot_path.relative_to(project)),
            'snapshot_encryption': {'mode': 'aes-256-gcm', 'key_env': 'TASKS_AES_KEY'},
        },
    }
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')

    monkeypatch.setenv('TASKS_AES_KEY', base64.b64encode(aes_key).decode('utf-8'))

    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--config',
        str(config_path),
        '--json',
    ])
    assert exit_code == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    enc_opts = payload['provider']['options']['snapshot_encryption']
    assert enc_opts['mode'] == 'aes-256-gcm'
    assert enc_opts['key_env'] == 'TASKS_AES_KEY'
    assert enc_opts.get('key') in (None, '***')



def test_tasks_sync_inline_provider_apply(project: Path, tmp_path: Path) -> None:
    remote = _write_remote(tmp_path)
    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--provider',
        'file',
        '--input',
        str(remote),
        '--apply',
    ])
    assert exit_code == 0

    board_path = project / 'data' / 'tasks.board.json'
    board_payload = json.loads(board_path.read_text(encoding='utf-8'))
    tasks = {task['id']: task for task in board_payload['tasks']}
    assert tasks['TASK-1']['status'] == 'in_progress'
    assert tasks['TASK-2']['status'] == 'done'
    assert tasks['TASK-3']['status'] == 'open'



def test_tasks_sync_inline_provider_option_path(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    provider_dir = project / 'state' / 'provider'
    provider_dir.mkdir(parents=True, exist_ok=True)
    snapshot = provider_dir / 'inline_tasks.json'
    remote = _write_remote(tmp_path)
    snapshot.write_text(remote.read_text(encoding='utf-8'), encoding='utf-8')

    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--provider',
        'file',
        '--provider-option', f'path={snapshot.relative_to(project)}',
        '--json',
    ])
    assert exit_code == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload['provider']['type'] == 'file'
    assert payload['applied'] is False
    assert payload['summary'] == {'total': 3, 'create': 1, 'update': 1, 'close': 1, 'unchanged': 0}
    board = json.loads((project / 'data' / 'tasks.board.json').read_text(encoding='utf-8'))
    status_map = {task['id']: task['status'] for task in board['tasks']}
    assert status_map['TASK-1'] == 'open'



def test_tasks_sync_inline_jira_snapshot(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = tmp_path / 'jira_inline.json'
    snapshot.write_text(
        json.dumps(
            {
                'issues': [
                    {
                        'key': 'TASK-1',
                        'fields': {'summary': 'Inline Jira Existing', 'status': {'name': 'In Progress'}},
                    },
                    {
                        'key': 'TASK-7',
                        'fields': {'summary': 'Inline Jira New', 'status': {'name': 'To Do'}},
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding='utf-8',
    )

    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--provider',
        'jira',
        '--provider-option', f'snapshot_path={snapshot}',
        '--json',
    ])
    assert exit_code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['summary'] == {'total': 3, 'create': 1, 'update': 1, 'close': 1, 'unchanged': 0}
    assert payload['provider']['type'] == 'jira'

    board = json.loads((project / 'data' / 'tasks.board.json').read_text(encoding='utf-8'))
    assert {task['id']: task['status'] for task in board['tasks']}['TASK-1'] == 'open'


def test_tasks_sync_inline_jira_encrypted(
    project: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if AESGCM is None:
        pytest.skip('cryptography not available')

    aes_key = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv('TASKS_AES_KEY', base64.b64encode(aes_key).decode('utf-8'))

    provider_dir = project / 'state' / 'provider'
    provider_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = _write_aes_snapshot(
        provider_dir,
        'jira_inline_aes.json',
        {
            'issues': [
                {
                    'key': 'TASK-1',
                    'fields': {'summary': 'Encrypted Jira Existing', 'status': {'name': 'Done'}},
                },
                {
                    'key': 'TASK-8',
                    'fields': {'summary': 'Encrypted Jira New', 'status': {'name': 'In Progress'}},
                },
            ]
        },
        aes_key,
    )

    rel_snapshot = snapshot_path.relative_to(project)
    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--provider',
        'jira',
        '--provider-option', f'snapshot_path={rel_snapshot}',
        '--provider-option', 'snapshot_encryption.mode=aes-256-gcm',
        '--provider-option', 'snapshot_encryption.key_env=TASKS_AES_KEY',
        '--json',
    ])
    assert exit_code == 0

    payload = json.loads(capsys.readouterr().out)
    enc_opts = payload['provider']['options']['snapshot_encryption']
    assert enc_opts['mode'] == 'aes-256-gcm'
    assert enc_opts['key_env'] == 'TASKS_AES_KEY'
    assert payload['summary']['create'] == 1


def test_tasks_sync_inline_github_snapshot(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = tmp_path / 'github_inline.json'
    snapshot.write_text(
        json.dumps(
            {
                'issues': [
                    {
                        'id': 1,
                        'number': 5,
                        'title': 'Inline GitHub Existing',
                        'state': 'closed',
                        'labels': [{'name': 'P1'}],
                    },
                    {
                        'id': 2,
                        'number': 9,
                        'title': 'Inline GitHub New',
                        'state': 'open',
                        'labels': [{'name': 'P0'}],
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding='utf-8',
    )

    exit_code = cli_main.main([
        'tasks',
        'sync',
        str(project),
        '--provider',
        'github',
        '--provider-option', f'snapshot_path={snapshot}',
        '--provider-option', 'owner=agentcontrol',
        '--provider-option', 'repo=sdk',
        '--json',
    ])
    assert exit_code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['provider']['type'] == 'github'
    assert payload['summary'] == {'total': 4, 'create': 2, 'update': 0, 'close': 2, 'unchanged': 0}

