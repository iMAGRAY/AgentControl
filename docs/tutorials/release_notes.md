# Tutorial: Автоматизированные релиз-ноты

`agentcall release notes` анализирует git-историю проекта и последние отчёты `verify`, чтобы сформировать Markdown и JSON релиз-ноты без ручного редактирования.

## 1. Базовый вызов
```bash
agentcall release notes --json
```
- Генерирует `reports/release_notes.md` и `reports/release_notes.json`.
- В JSON попадает сводка (количество коммитов, участники, секции), на stdout выводится тот же JSON.

## 2. Диапазон коммитов
- `--from-ref v0.5.0` — нижняя граница (исключительно).
- `--to-ref HEAD` — верхняя граница (по умолчанию `HEAD`).
- `--max-commits 200` — ограничить количество анализируемых коммитов, если нет тегов.

Пример:
```bash
agentcall release notes --from-ref v0.5.1 --to-ref main --json
```

## 3. Куда сохранять Markdown
```bash
agentcall release notes --output reports/releases/v0.6.md
```
JSON при использовании `--json` попадёт рядом (`v0.6.json`).

## 4. Что попадает в отчёт
- Группировка по типам коммитов (`feat/ fix/ chore/...`), секции сортируются по активности.
- Список авторов (по данным git).
- Блок **Quality Gate**: берётся из последнего `reports/verify.json` (время, код возврата, список упавших шагов).

## 5. Рекомендации
- Делайте теги перед запуском, чтобы `--from-ref` мог сослаться на предыдущий релиз.
- Убедитесь, что `reports/verify.json` актуален — `scripts/verify.sh` перед релизом.
- Стандартизируйте сообщения коммитов (Conventional Commits), чтобы секции заполнялись корректно.
