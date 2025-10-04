# AgentControl Universal Agent SDK

Корпоративный SDK для автономных инженеров и агентных команд. Платформа обеспечивает единый операционный контур, надежный набор команд и готовую инфраструктуру, превращая любую кодовую базу в управляемую среду разработки с нулевым временем запуска.

## 1. Ценность и позиционирование
- **Единая точка входа.** Команды и агенты работают через CLI `agentcall`, получая согласованные пайплайны, отчёты и статусы независимо от стека.
- **Гарантированная управляемость.** Артефакты архитектуры, дорожная карта и статус борда синхронизируются автоматически, исключая ручной дрейф.
- **Готовность для ИИ-агентов.** Авторизация Codex/Claude, Memory Heart и пакет инструментов разворачиваются без ручных шагов, что минимизирует когнитивную нагрузку.
- **Комплаенс по умолчанию.** Локфайлы, SBOM, аудит качества и выпуска интегрированы в стандартный пайплайн.

## 2. Архитектура решения
| Слой | Ответственность | Основные артефакты |
| --- | --- | --- |
| **CLI & Pipelines** | Управление жизненным циклом команд (`init`, `verify`, `ship`, `status`). | `src/agentcontrol/cli`, `src/agentcontrol/app` |
| **Domain & Governance** | Модели капсулы, шаблонов и команд, гарантия инвариантов. | `src/agentcontrol/domain`, `src/agentcontrol/ports` |
| **Шаблоны** | Готовые капсулы (`default`, `python`, `node`, `monorepo`) с инфраструктурой внутри `./agentcontrol/`. | `src/agentcontrol/templates/<version>/<template>` |
| **Плагины** | Расширение CLI через entry point `agentcontrol.plugins`. | `src/agentcontrol/plugins`, `examples/plugins/` |
| **Наблюдаемость и телеметрия** | Структурированные события в `~/.agentcontrol/logs/`, Memory Heart, отчёты. | `src/agentcontrol/utils/telemetry`, `reports/` |

## 3. Быстрый старт (на новой машине)
1. **Предпосылки.** Bash ≥ 5.0, Python ≥ 3.10, Node.js ≥ 18, Cargo ≥ 1.75. Для CI фиксируйте версии инструментов.
2. **Глобальная установка SDK.**
   ```bash
   ./scripts/install_agentcontrol.sh
   pipx install agentcontrol  # либо python3 -m pip install agentcontrol
   ```
   Шаблоны размещаются в `~/.agentcontrol/templates/<channel>/<version>`, CLI доступен как `agentcall`.
3. **Развёртывание капсулы проекта.**
   ```bash
   agentcall status ~/workspace/project   # автоинициализация капсулы default@stable
   # или явное управление
   agentcall init --template python ~/workspace/project
   ```
   Все артефакты SDK размещаются в каталоге `project/agentcontrol/`, основная кодовая база остаётся нетронутой.
4. **Аутентификация агентов.**
   ```bash
   cd ~/workspace/project
   agentcall agents auth
   agentcall agents status
   ```
   Токены сохраняются под `~/.agentcontrol/state/`.
5. **Квалификация окружения.**
   ```bash
   agentcall verify
   ```
   Пайплайн выполняет форматирование, тесты, безопасность, синхронизацию архитектуры, Memory Heart и формирует `reports/verify.json`.

## 4. Командный справочник
| Команда | Назначение | Параметры/заметки |
| --- | --- | --- |
| `agentcall status [PATH]` | Дашборд программы, автоинициализация капсулы. | Переменные `AGENTCONTROL_DEFAULT_TEMPLATE`, `AGENTCONTROL_DEFAULT_CHANNEL`, `AGENTCONTROL_NO_AUTO_INIT` |
| `agentcall init/upgrade` | Первичная инициализация или миграция шаблона. | Шаблоны `default`, `python`, `node`, `monorepo` |
| `agentcall setup` | Системные и проектные зависимости, установка CLI агентов. | `SKIP_AGENT_INSTALL`, `SKIP_HEART_SYNC` |
| `agentcall verify` | Стандарт качества: fmt/lint/tests/coverage/security/docs/SBOM. | `VERIFY_MODE`, `CHANGED_ONLY`, `JSON=1` |
| `agentcall fix` | Автопочинки из `config/commands.sh`. | Используйте после локальных правок |
| `agentcall review` | Дифф-ревью с отчётом и diff-cover. | `REVIEW_BASE_REF`, `REVIEW_SAVE` |
| `agentcall ship` | Релизный гейт (verify → релиз-хореография). | Блокирует при открытых микрозадачах или красных проверках |
| `agentcall agents …` | Управление CLI агентов (install/auth/status/logs/workflow). | Конфиг `config/agents.json` |
| `agentcall heart …` | Обслуживание Memory Heart (`sync`, `query`, `serve`). | Настройки в `config/heart.json` |
| `agentcall templates` | Перечень установленных шаблонов. | Каналы `stable`, `nightly` |
| `agentcall telemetry …` | Работа с локальной телеметрией. | `report`, `tail --limit`, `clear` |
| `agentcall plugins …` | Управление плагинами (`list`, `install`, `remove`, `info`). | Entry point `agentcontrol.plugins` |

## 5. Шаблоны капсул
| Шаблон | Сценарий | Особенности |
| --- | --- | --- |
| `default` | Полный контур управления (архитектура, дорожная карта, отчёты). | Готовые скрипты `verify/fix/ship`, документация, Memory Heart |
| `python` | Backend на Python + pytest. | Автоматическая работа в `agentcontrol/.venv`, sample tests |
| `node` | Node.js сервисы с ESLint и `node --test`. | Сценарии npm завернуты в капсулу |
| `monorepo` | Python backend + Node фронтенд. | Сквозные пайплайны для обоих пакетов |

Шаблоны содержат всю инфраструктуру внутри `agentcontrol/`; собственные шаблоны добавляйте в `src/agentcontrol/templates/<version>/<name>` и обновляйте `template.json`.

## 6. Релиз и поставка
1. Обновите версию: `src/agentcontrol/__init__.py`, `pyproject.toml`, changelog.
2. Соберите выпуск: `./scripts/release.sh` (wheel, sdist, SHA256, manifest).
3. Публикация (опционально): `python -m twine upload dist/*`.
4. Для офлайн-установки передайте `.whl` и `agentcontrol.sha256`, затем `pipx install --force <wheel>`.

## 7. Наблюдаемость и телеметрия
- Все события локальные, хранятся в `~/.agentcontrol/logs/telemetry.jsonl`. Опция `AGENTCONTROL_TELEMETRY=0` отключает сбор.
- Memory Heart размещается в `agentcontrol/state/heart/`, доступ через `agentcall heart query` и `agentcall heart serve`.
- Отчёты: `reports/verify.json`, `reports/status.json`, `reports/review.json`, `reports/doctor.json`.

## 8. Сервисная модель
- Владелец продукта: архитектурная группа (см. `AGENTS.md`).
- Операционное окно: 24/7, SLA на ответы агентов определяется программой эксплуатации.
- Канал поддержки: задачи через `agentcall agents workflow --task=<ID>` либо direct ping владельца из `AGENTS.md`.

## 9. Часто задаваемые вопросы
**В:** Можно ли отключить автоинициализацию?
**О:** Да, экспортируйте `AGENTCONTROL_NO_AUTO_INIT=1` перед запуском `agentcall`.

**В:** Как добавить собственный пайплайн?
**О:** Дополните `agentcontrol/agentcall.yaml` и `config/commands.sh`; команда появится в `agentcall commands`.

**В:** Где хранится состояние?
**О:** В каталоге капсулы `agentcontrol/state/` (проект) и в `~/.agentcontrol/state/` (глобальные настройки, registry).

---
© AgentControl — универсальный SDK для агентных команд.
