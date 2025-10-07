# Sample Gallery

`agentcall gallery` предоставляет готовые примеры проектов для быстрого старта ИИ-агентов.

## 1. Просмотр списка
```bash
agentcall gallery list --json
```
Вывод включает `id`, описание, теги, оценку размера и путь к исходному каталогу.

## 2. Загрузка проекта
```bash
agentcall gallery fetch python-minimal --dest /tmp/gallery
```
- По умолчанию создаётся ZIP (`python-minimal.zip`).
- Добавьте `--directory`, чтобы скопировать структуру папок (без архивации).
- Путь `/tmp/gallery` создаётся автоматически; существующий ZIP перезаписан не будет.

## 3. Примеры
- `python-minimal` — FastAPI‑сервис с `/healthz`.
- `monorepo-slim` — монорепозиторий с FastAPI backend и Vite/React frontend.

Оба примера весят менее 30 МиБ и совместимы с шаблоном `.agentcontrol`.

## 4. Рекомендации
- Используйте `agentcall quickstart --template <type>` внутри скачанного проекта для настройки капсулы.
- Храните скачанные архивы в отдельной директории, чтобы не засорять рабочий репозиторий.
