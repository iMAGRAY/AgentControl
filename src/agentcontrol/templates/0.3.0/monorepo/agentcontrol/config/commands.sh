# Monorepo workflows: Python backend + Node web

SDK_MONO_ROOT="agentcontrol"
backend_dir="$SDK_MONO_ROOT/packages/backend"
web_dir="$SDK_MONO_ROOT/packages/web"

SDK_DEV_COMMANDS=(
  "(cd ${backend_dir} && [ -d .venv ] || python3 -m venv .venv)"
  "(cd ${backend_dir} && .venv/bin/pip install --upgrade pip)"
  "(cd ${backend_dir} && .venv/bin/pip install -r requirements.txt)"
  "(cd ${web_dir} && npm install)"
)

SDK_VERIFY_COMMANDS=(
  "(cd ${backend_dir} && .venv/bin/pip install -r requirements.txt)"
  "(cd ${backend_dir} && .venv/bin/python -m pytest -q)"
  "(cd ${web_dir} && npm run lint)"
  "(cd ${web_dir} && npm test)"
)

SDK_FIX_COMMANDS=(
  "(cd ${web_dir} && npm run lint -- --fix)"
)

SDK_SHIP_COMMANDS=(
  "(cd ${backend_dir} && .venv/bin/python -m build)"
  "(cd ${web_dir} && npm run build || echo \"configure build script\")"
)

SDK_TEST_COMMAND="(cd ${backend_dir} && .venv/bin/python -m pytest -q) && (cd ${web_dir} && npm test)"
