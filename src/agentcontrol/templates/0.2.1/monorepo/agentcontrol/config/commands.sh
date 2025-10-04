# Monorepo workflows: Python backend + Node web

backend_venv="packages/backend/.venv"
node_dir="packages/web"

SDK_DEV_COMMANDS=(
  "(cd packages/backend && [ -d .venv ] || python3 -m venv .venv)"
  "(cd packages/backend && .venv/bin/pip install --upgrade pip)"
  "(cd packages/backend && .venv/bin/pip install -r requirements.txt)"
  "(cd packages/web && npm install)"
)

SDK_VERIFY_COMMANDS=(
  "(cd packages/backend && .venv/bin/pip install -r requirements.txt)"
  "(cd packages/backend && .venv/bin/python -m pytest -q)"
  "(cd packages/web && npm run lint)"
  "(cd packages/web && npm test)"
)

SDK_FIX_COMMANDS=(
  "(cd packages/web && npm run lint -- --fix)"
)

SDK_SHIP_COMMANDS=(
  "(cd packages/backend && .venv/bin/python -m build)"
  "(cd packages/web && npm run build || echo 'configure build script')"
)

SDK_TEST_COMMAND="(cd packages/backend && .venv/bin/python -m pytest -q) && (cd packages/web && npm test)"
