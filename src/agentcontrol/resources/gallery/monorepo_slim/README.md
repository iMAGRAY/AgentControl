# Monorepo Slim Sample

Демонстрация лёгкого монорепозитория с Python backend и Node frontend, ориентированного на шаблон `monorepo`.

## Структура
- `backend/` — FastAPI сервис (порт 8000).
- `frontend/` — Vite + React SPA (порт 5173).

## Быстрый старт
```bash
# Backend
cd backend
uvicorn api.main:app --reload

# Frontend
cd ../frontend
npm install
npm run dev
```
