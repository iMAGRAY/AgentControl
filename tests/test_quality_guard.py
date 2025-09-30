import json
import os
import subprocess
from pathlib import Path

def init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE)


def run_guard(tmp_path: Path, include_untracked: bool = True) -> dict:
    args = ["python3", str(Path(__file__).resolve().parents[1] / "scripts" / "lib" / "quality_guard.py"), "--base", "HEAD"]
    if include_untracked:
        args.append("--include-untracked")
    result = subprocess.run(args, cwd=tmp_path, check=True, stdout=subprocess.PIPE)
    return json.loads(result.stdout.decode("utf-8"))


def test_detects_secret_in_new_directory(tmp_path: Path, monkeypatch):
    init_repo(tmp_path)
    secret_dir = tmp_path / "lib" / "new"
    secret_dir.mkdir(parents=True)
    (secret_dir / "creds.py").write_text("API_KEY = 'AKIA1234567890ABCDEFFF'\n", encoding="utf-8")
    report = run_guard(tmp_path)
    findings = {(f["file"], f["pattern"]) for f in report["findings"]}
    assert ("lib/new/creds.py", "aws_access_key") in findings


def test_skips_large_file(tmp_path: Path):
    init_repo(tmp_path)
    large = tmp_path / "lib" / "blob.bin"
    large.parent.mkdir(parents=True)
    large.write_bytes(b"0" * (3 * 1024 * 1024))
    report = run_guard(tmp_path)
    assert "lib/blob.bin" not in report["files_scanned"]


def test_targets_config_files(tmp_path: Path):
    init_repo(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "vars.tf").write_text("variable \"api_token\" { default = \"sk_live_1234567890abcdefABCDEF\" }\n", encoding="utf-8")
    report = run_guard(tmp_path)
    findings = {(f["file"], f["pattern"]) for f in report["findings"]}
    assert ("config/vars.tf", "stripe_secret_key") in findings
