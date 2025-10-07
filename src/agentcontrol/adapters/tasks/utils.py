"""Shared helpers for task provider adapters."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AESGCM = None

from agentcontrol.ports.tasks.provider import TaskProviderError


def read_snapshot(
    path: str,
    *,
    mode: str | None = None,
    key: str | None = None,
    key_env: str | None = None,
) -> Any:
    """Load a JSON snapshot, optionally decrypting it with the requested mode."""

    file_path = Path(path)
    if not file_path.exists():
        raise TaskProviderError(f"snapshot not found at {file_path}")

    payload_text = file_path.read_text(encoding="utf-8")
    if not mode:
        return _loads_json(payload_text)

    mode = mode.lower().strip()
    secret = _resolve_key(key=key, key_env=key_env)

    if mode == "xor":
        try:
            decoded = base64.b64decode(payload_text)
        except (base64.binascii.Error, ValueError) as exc:
            raise TaskProviderError("encrypted snapshot is not valid base64") from exc
        decrypted = _xor_cipher(decoded, secret.encode("utf-8"))
        return _loads_json_bytes(decrypted)

    if mode in {"aes-256-gcm", "aes256gcm", "aes_gcm"}:
        if AESGCM is None:
            raise TaskProviderError("aes-gcm mode requires 'cryptography' package")
        key_bytes = _decode_key_bytes(secret)
        if len(key_bytes) not in {16, 24, 32}:
            raise TaskProviderError("aes-gcm key must be 16, 24 or 32 bytes")
        try:
            blob = base64.b64decode(payload_text)
        except (base64.binascii.Error, ValueError) as exc:
            raise TaskProviderError("aes-gcm snapshot is not valid base64") from exc
        if len(blob) <= 28:
            raise TaskProviderError("aes-gcm snapshot payload too short")
        nonce = blob[:12]
        ciphertext_with_tag = blob[12:]
        aesgcm = AESGCM(key_bytes)
        try:
            decrypted = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        except Exception as exc:  # pragma: no cover — exact error depends on backend
            raise TaskProviderError("aes-gcm decryption failed") from exc
        return _loads_json_bytes(decrypted)

    raise TaskProviderError(f"tasks.sync.config_invalid: unsupported encryption mode '{mode}'")


def _resolve_key(*, key: str | None, key_env: str | None) -> str:
    if key:
        return key
    if key_env:
        value = os.environ.get(key_env)
        if value:
            return value
        raise TaskProviderError(f"encryption key environment variable '{key_env}' is not set")
    raise TaskProviderError("encrypted snapshots require 'key' or 'key_env'")


def _xor_cipher(data: bytes, key: bytes) -> bytes:
    if not key:
        raise TaskProviderError("encryption key must not be empty")
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def _decode_key_bytes(secret: str) -> bytes:
    for decoder in (_try_base64, _try_hex):
        decoded = decoder(secret)
        if decoded is not None:
            return decoded
    return secret.encode("utf-8")


def _try_base64(value: str) -> bytes | None:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error):
        return None


def _try_hex(value: str) -> bytes | None:
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


def _loads_json(payload: str) -> Any:
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TaskProviderError("snapshot is not valid JSON") from exc


def _loads_json_bytes(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskProviderError("decrypted snapshot is not valid JSON") from exc


__all__ = ["read_snapshot"]
