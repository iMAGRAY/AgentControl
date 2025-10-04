# AgentControl — Корпоративный регламент выпуска

1. **Предрелизная проверка.**
   ```bash
   .venv/bin/python -m pytest
   ```
   Рабочее дерево должно быть чистым, тесты — зелёные.
2. **Версионирование.** Обновите `src/agentcontrol/__init__.py`, `pyproject.toml`, добавьте запись в `docs/changes.md`.
3. **Сборка артефактов.**
   ```bash
   ./scripts/release.sh
   ```
   Скрипт создаёт wheel и sdist в `dist/`, считает SHA256 (`agentcontrol.sha256`) и формирует `release-manifest.json`.
4. **Актуализация changelog (опционально).**
   ```bash
   ./scripts/changelog.py "Краткое описание изменений"
   git add docs/changes.md
   ```
5. **Публикация (если требуется PyPI).**
   ```bash
   python -m twine upload dist/*
   ```
6. **Тэгирование и пуш.**
   ```bash
   git tag -s vX.Y.Z -m "agentcontrol vX.Y.Z"
   git push origin main --tags
   ```
7. **Коммуникация.** Обновите README (секция «Быстрый старт»), отправьте релиз-заметки заинтересованным сторонам.
8. **Пострелизный контроль.**
   ```bash
   pipx install agentcontrol==X.Y.Z
   agentcall init ~/tmp/demo
   agentcall verify
   ```
   Фиксируйте результаты в `reports/release-validation.json` (при необходимости).
