# SDK commands tailored for the monorepo template (Python backend + Node web).

SDK_MONO_ROOT="agentcontrol"
BACKEND_DIR="$SDK_MONO_ROOT/packages/backend"
WEB_DIR="$SDK_MONO_ROOT/packages/web"

SDK_DEV_COMMANDS=(
  "(cd ${BACKEND_DIR} && [ -d .venv ] || python3 -m venv .venv)"
  "(cd ${BACKEND_DIR} && .venv/bin/pip install --upgrade pip)"
  "(cd ${BACKEND_DIR} && .venv/bin/pip install -r requirements.txt)"
  "(cd ${WEB_DIR} && npm install)"
)

SDK_VERIFY_COMMANDS=(
  "(cd ${BACKEND_DIR} && .venv/bin/pip install -r requirements.txt)"
  "(cd ${BACKEND_DIR} && (.venv/bin/python -m pytest -q || [[ $? -eq 5 ]]))"
  "(cd ${WEB_DIR} && npm run lint)"
  "(cd ${WEB_DIR} && npm test)"
)

SDK_FIX_COMMANDS=(
  "(cd ${WEB_DIR} && npm run lint -- --fix)"
)

SDK_SHIP_COMMANDS=(
  "(cd ${BACKEND_DIR} && .venv/bin/python -m build)"
  "(cd ${WEB_DIR} && npm run build)"
)

SDK_TEST_COMMAND="(cd ${BACKEND_DIR} && .venv/bin/python -m pytest -q) && (cd ${WEB_DIR} && npm test)"
