# Python Minimal Sample

Этот пример демонстрирует минимальный каркас Python‑сервиса, совместимый с `agentcall init --template python`.

## Состав
- `pyproject.toml` — конфигурация Poetry/PEP 621 с зависимостью `fastapi`.
- `src/app.py` — приложение с одним эндпоинтом `GET /healthz`.

## Запуск
```bash
uvicorn app:app --reload
```
