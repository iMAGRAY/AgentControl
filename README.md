# GPT-5 Codex SDK Toolkit

SDK предназначен для того, чтобы агент GPT‑5 Codex сразу получал управляемую, воспроизводимую и проверяемую среду разработки. Всё, что связано с запуском процессов качества, дорожной картой и доской задач, доступно в виде преднастроенных команд, поэтому агент фокусируется на работе, а не на обвязке.

## Быстрый старт
1. `make setup` — устанавливает системные утилиты (shellcheck, go и т.п.), разворачивает `.venv`, ставит Python/Go-зависимости (pytest, diff-cover, detect-secrets, reviewdog) и автоматически подтягивает CLI Codex/Claude и Memory Heart индекс.
2. `make lock` — регенерирует `requirements.lock` (с `pip-compile --generate-hashes`) и `sbom/python.json`, гарантируя совпадение версий и SHA256-хешей.
3. `make verify` — выполняет проверки/тесты, сверяет окружение с lock/SBOM, запускает `pip-audit`, актуализирует Memory Heart (если нужно) и сохраняет отчёт `reports/verify.json`. GitHub Actions гоняет эту цепочку на каждом push/PR и по ночному расписанию (03:00 UTC), выкладывая SARIF в Security Alerts.

## Концепция
- **Единый контрольный центр.** Команда `make status` печатает синхронный срез Roadmap+TaskBoard и сохраняет JSON-отчёт `reports/status.json`, поэтому прогресс программы (фазы MVP→Q7) и фокус-задачи видны с одного взгляда.
- **Полностью автоматизированные ритуалы.** `make init/dev/verify/fix/ship` запускают стандартизированные скрипты; дорожная карта и доска задач валидируются автоматически, исключая дрейф и ручные проверки.
- **Хэшированный lock + SBOM.** `make lock` и `make verify` сверяют `requirements.lock` с воспроизводимым `pip-compile` и гарантируют, что окружение соответствует хешам и опубликованному SBOM.
- **Минимальная когнитивная нагрузка.** Форматы YAML/JSON и журнал событий скрыты за CLI. Агент использует команды верхнего уровня (`make init`, `make task add/take/done/history`) вместо прямого редактирования файлов.
- **Архитектурный манифест.** `architecture/manifest.yaml` описывает программу, системы, ADR/RFC и задачи; `make architecture-sync` регенерирует все производные артефакты, исключая дрейф.
- **Автоматический пересчёт прогресса.** `make progress` читает `architecture/manifest.yaml` и `todo.machine.md`, пересчитывает доли выполнения Big Tasks/эпиков/программы и синхронизирует YAML-блоки.
- **Автосогласование Roadmap.** Прогресс вычисляется из task board; при расхождении с ручными полями выводятся предупреждения, не прерывая поток.
- **Сердце памяти.** `make heart-sync` строит локальный векторный индекс исходников и документов; запросы (`make heart-query`) мгновенно находят релевантные фрагменты для людей и ИИ.
- **Совместная работа без конфликтов.** Каждое действие фиксируется в `journal/task_events.jsonl`, атомарные обновления исключают гонки, а проверки блокеров/зависимостей/конфликтов предотвращают одновременный захват несовместимых задач.
- **Дифф-фокусированное ревью.** `make review` строит diff относительно базового коммита, запускает линтеры/тесты только по изменённым файлам, фиксирует длительности шагов и сохраняет отчёт `reports/review.json` без остановки потока.

## Возможности
- Стандартизированные команды `make init/dev/verify/fix/ship` с единым поведением и автоматической генерацией каркаса.
- Высокопроизводительный CLI `make task …` (Python ядро с файловыми блокировками и кэшем) устойчив к одновременной работе десятков и сотен агентов, включает команду `make task metrics`.
- Единый дашборд статуса (`make status`) + детальный отчёт `make roadmap`, автоматически синхронизирующие `todo.machine.md` по данным task board.
- Доска задач корпоративного уровня через `make task add/take/drop/done/status/summary/conflicts/comment/history/validate` с атомарными обновлениями и JSONL-журналом.
- Конфигурация через `config/commands.sh` — задайте стек-специфичные сценарии без правок скриптов.
- Политики качества управляются через `config/commands.sh`: массив `SDK_REVIEW_LINTERS`, команда `SDK_TEST_COMMAND` и `SDK_COVERAGE_FILE` используются в `make review`, а `SDK_VERIFY_COMMANDS` — в `make verify`.
- Если оставить значения по умолчанию (`echo 'configure …'`), SDK автоматически подставит команды для обнаруженных стеков (npm/Yarn/pnpm, Poetry/Pipenv, Go, Cargo, Gradle/Maven, .NET, Bundler и др.), оборачивая их защитой от отсутствующих инструментов.
- Преднастроенные политики форматирования (`.editorconfig`), игнорирования (`.codexignore`, `.gitignore`, `state/`, `journal/`, `reports/`).
- Обязательная структура документации (`AGENTS.md`, `todo.machine.md`) поддерживается автоматически (`make init`, `make status`).
- Автоматическая проверка shell-скриптов через `shellcheck`, если утилита установлена.

## Memory Heart & ИИ-агенты
- `make agents-install` — готовит CLI Codex/Claude (или устанавливает заглушку, если бинарь недоступен).
- `make heart-sync` — строит локальный индекс (инкрементально); `make heart-query Q="..."` возвращает релевантные чанки в табличном/JSON-формате, `make heart-serve` поднимает лёгкий HTTP-сервис.
- `make agent-assign TASK=… AGENT=codex` — собирает контекст (прогресс, roadmap, Memory Heart, git diff), вызывает выбранный агент и сохраняет лог + комментарий в задаче.
- `make agent-plan TASK=…` / `make agent-analysis` — генерируют план действий или высокоуровневый обзор (при отсутствии CLI возвращают детерминированную подсказку).
- Параметры ролей, sandbox и каталогов логов управляются в `config/agents.json`; Memory Heart конфигурируется через `config/heart.json`.

## Быстрый старт
1. Выполните `make init` — будут созданы конфиги, стартовая roadmap/task board, журнал и отчёт `reports/status.json`.
2. Выполните `make arch-edit`, отредактируйте `architecture/manifest.edit.yaml` (цели, системы, задачи) и примените изменения `make arch-apply` — все производные файлы (`todo.machine.md`, `data/tasks.board.json`, `docs/architecture/overview.md`, ADR/RFC) обновятся автоматически.
3. Запустите `make dev` для просмотра quickref и проверки конфигурации.
4. Работайте с задачами:
   - `make task-take [AGENT=<имя>]` — взять следующую доступную задачу (учёт блокеров/конфликтов).
   - `make task-drop TASK=<id>` — освободить задачу (статус -> ready).
   - `make task-done TASK=<id> [AGENT=...]` — отметить задачу выполненной.
   - `make task-add TITLE="..." [EPIC=...] [BIG_TASK=...]` — создать новую задачу без редактирования JSON и связать её с Big Task.
   - `make task comment TASK=<id> MESSAGE="..."` — вести журнал обсуждений.
   - `LIMIT=20 [JSON=1] make task-history` — посмотреть последние события или получить JSON. 
5. В любой момент выполняйте `make status`, чтобы увидеть Roadmap + TaskBoard и обновить `reports/status.json`; для полного цикла агента используйте `make agent-cycle` (sync → verify → отчёт `reports/agent_runs/<ts>.yaml`).
6. Перед коммитом запускайте `make verify` — отчёт `reports/verify.json` фиксирует статусы, длительности и предупреждения. Для фокусного ревью изменений используйте `make review` — команда соберёт diff, запустит `SDK_REVIEW_LINTERS`/`SDK_TEST_COMMAND`, выполнит realness & secrets чек по рабочему дереву и сохранит `reports/review.json`.
7. Перед публикацией запускайте `make ship`: скрипт повторно вызывает `make verify`, читает `reports/verify.json` и блокирует выпуск, если в отчёте есть упавшие шаги или findings.
8. Для диагностики окружения выполните `make doctor` или `python3 scripts/sdk.py doctor` — отчёт `reports/doctor.json` перечислит недостающие зависимости и команды установки.

### Memory Heart & AI Agents

- `make agents-install` — подтягивает/линкует CLI Codex и Claude (создаёт заглушку при отсутствии бинаря). Повторно вызывайте после обновления субмодулей или смены окружения.
- `make heart-sync` — индексирует код и документацию; `make heart-query Q="…" [FORMAT=json]` и `make heart-serve` используют тот же индекс для поиска релевантных фрагментов.
- `make agent-assign TASK=ARCH-001 AGENT=codex [ROLE="Tech Lead"]` — формирует роли, подтягивает прогресс, Memory Heart, git diff и вызывает выбранный агент. Ответ логируется в `reports/agents/<timestamp>.log`, комментарий автоматически добавляется в задачу.
- `make agent-plan TASK=…` / `make agent-analysis` — генерируют пошаговый план или обзор. Если CLI недоступен, возвращают детерминированные подсказки, чтобы пайплайн оставался предсказуемым.

Настройки лежат в `config/agents.json` (роли, sandbox, владельцы) и `config/heart.json` (фильтры файлов, параметры чанков). Индекс хранится локально (`context/heart`) и автоматически обновляется в `make setup`/`make verify` (можно пропустить через `SKIP_HEART_SYNC=1`).

### Качество и ревью

- `make verify` выполняет архитектурные и структурные проверки, shellcheck, quality-guard (поиск заглушек/секретов) и пользовательские `SDK_VERIFY_COMMANDS` (или автоопределённые команды). Все шаги попадают в `reports/verify.json` с длительностями и логами; предупреждения не прерывают выполнение, строгий режим включается `EXIT_ON_FAIL=1`.
- `make review [REVIEW_BASE_REF=<ref>]` строит diff против базового коммита, запускает `SDK_REVIEW_LINTERS`, `SDK_TEST_COMMAND`, optional `diff-cover`, quality-guard по рабочему дереву и сохраняет `reports/review.json`.
- `SDK_COVERAGE_FILE` (например, `coverage.xml`) + `diff-cover` позволяют контролировать покрытие по изменённым строкам. Если `diff-cover` не установлен, шаг помечается предупреждением.
- Найденные заглушки/секреты фиксируются как предупреждения, но `make ship` остановит релиз, если `quality_guard` сообщает findings.

### Зависимости и инструменты

| Инструмент | Назначение | Установка (Ubuntu/Debian) |
|------------|------------|---------------------------|
| `pytest`   | запуск встроенных тестов (`tests/`) | `pip install pytest` |
| `diff-cover` | покрытие по изменённым строкам | `pip install diff-cover` |
| `reviewdog` | консолидация линтеров в `make review` | `go install github.com/reviewdog/reviewdog/cmd/reviewdog@latest` |
| `detect-secrets` | расширенный поиск секретов | `pip install detect-secrets` |
| `nbconvert`, `jupytext` | поддержка будущего флага `REVIEW_SAVE=1` | `pip install nbconvert jupytext` |

SDK корректно пропускает отсутствующие инструменты, но для максимальной диагностики рекомендуется установить хотя бы `pytest` и `diff-cover`.

### Тесты

В репозитории добавлены smoke-тесты (`tests/test_quality_guard.py`, `tests/test_auto_detect.py`). Запуск: `pytest` (например, `python3 -m venv .venv && source .venv/bin/activate && pip install pytest && pytest`). Автоопределение команд добавит `pytest` к `SDK_TEST_COMMAND`, если утилита доступна в PATH.

### Универсальный CLI

Помимо make-таргетов доступен Python-CLI: `python3 scripts/sdk.py <command>`. Поддерживаются `verify`, `review [--base <commit>]`, `doctor`, `status`, `summary`, `task ...`, `make <target>` и `qa` (цепочка `verify` → `review`). Это снижает когнитивную нагрузку, если хочется управлять SDK без Make.

## Доска задач
- Структура: состояние в `data/tasks.board.json`, оперативный state `state/task_state.json`, журнал `journal/task_events.jsonl`.
Roadmap синхронизируется автоматически при `make status`/`make verify` (см. `scripts/sync-roadmap.sh`).
- `make task status` группирует задачи по статусам, подсвечивает фокус и критерии успеха/провала.
- `make task summary --json` выдаёт машинно-читаемую сводку (для автоматизации, CI, интеграций).
- `make task metrics [--json]` — оперативные метрики (WIP по агентам, throughput 24h, готовые незахваченные задачи) для калибровки загрузки.
- `make task grab` учитывает приоритеты (P0→P3), блокеры, зависимости и конфликты — задача берётся только если это безопасно; при необходимости можно задействовать `FORCE=1`.
- Все действия записываются в JSONL-журнал; `BIG_TASK` помогает автоматически отражать прогресс в roadmap.
- Если переменная `AGENT` не указана, используется значение по умолчанию `gpt-5-codex`.

### Качество и ревью

- `make verify` выполняет архитектурные и структурные проверки, shellcheck, quality-guard (поиск заглушек/секретов) и пользовательские `SDK_VERIFY_COMMANDS` (или автоопределённые команды). Результат фиксируется в `reports/verify.json`; команда не прерывает работу даже при ошибках (если нужен строгий режим, установите `EXIT_ON_FAIL=1`).
- `make review [REVIEW_BASE_REF=<ref>]` строит diff против базового коммита, запускает `SDK_REVIEW_LINTERS`, `SDK_TEST_COMMAND`, optional `diff-cover`, quality-guard только по изменённым строкам и сохраняет `reports/review.json`. Переменные `REVIEW_SAVE=1 REVIEW_FORMAT=md|html|ipynb` зарезервированы под расширяемую отчётность; пока поддерживается вывод в JSON/терминал.
- `SDK_COVERAGE_FILE` (например, `coverage.xml`) + `diff-cover` позволяют контролировать покрытие по изменённым строкам. Если `diff-cover` не установлен, шаг помечается предупреждением.
- По умолчанию найденные заглушки/секреты фиксируются как предупреждения. Чтобы превратить их в ошибки, задайте `EXIT_ON_FAIL=1`.

## Настройка команд
Файл `config/commands.sh` экспортирует массивы Bash:
```bash
SDK_VERIFY_COMMANDS=("npm run lint" "npm test")
SDK_FIX_COMMANDS=("npm run lint -- --fix")
```
Команды выполняются по порядку; на любом возврате <>0 запуск прерывается.

## Структура управления
- `AGENTS.md` — единый интерфейс управления проектом (quickref печатается через `make dev`).
- `architecture/manifest.yaml` — единственный источник данных об архитектуре, дорожной карте и задачах.
- `docs/architecture/overview.md`, `docs/adr/*`, `docs/rfc/*` — генерируются из манифеста.
- `todo.machine.md` — глобальное планирование (Program → Epics → Big Tasks) с фазами MVP/Q1…Q7 (генерируется).
- `data/tasks.board.json` — доска задач с критериями успеха/провала (генерируется).
- `state/task_state.json` — оперативное состояние назначений.
- `journal/task_events.jsonl` — журнал истории событий.
- `reports/status.json` и `reports/architecture-dashboard.json` — последние срезы статуса и архитектуры.
- Микро-задачи фиксируйте через Update Plan Tool Codex CLI.

## Расширение
- Добавляйте дополнительные утилиты в `scripts/lib/` и подключайте их из целевых скриптов.
- Создавайте `docs/adr/` для архитектурных решений, ведите журнал в `docs/changes.md`.
- При необходимости добавьте статический анализ для стеков (пример: `SDK_VERIFY_COMMANDS+=("poetry run mypy")`).

## Требования
- Bash ≥ 5.0, make ≥ 4.0, python ≥ 3.8.
- (Опционально) `shellcheck` для статического анализа скриптов.

## Поддержка
Оператор или агент обновляют `AGENTS.md`, `todo.machine.md`, `data/tasks.board.json` и фазовые проценты при каждом значимом изменении. Регулярно запускайте `make status` и `make task history`, чтобы команда и агенты видели актуальный контекст.

## Тестирование
Формальные проверки в CI выполняются через `make verify`, который подготавливает виртуальное окружение `.venv`, устанавливает зависимости из `requirements.txt` и запускает `.venv/bin/python -m pytest -q`.

### Локальное воспроизведение
> Быстрый путь: `make setup` — создаст окружение и установит зависимости автоматически.

1. Создайте окружение: `python3 -m venv --upgrade-deps .venv`.
2. Обновите зависимости: `.venv/bin/pip install --upgrade -r requirements.txt` (фиксирует pytest 8.4.2).
3. Выполните тесты: `.venv/bin/python -m pytest -q`.

При необходимости можно запустить `make verify` для полного набора проверок SDK.

> `make verify` сверяет только те артефакты, что находятся под управлением генератора (см. `.sdk/arch/state.json`). Чтобы принять файл под автогенерацию, выполните `ARCH_TOOL_FORCE=1 make architecture-sync`.
