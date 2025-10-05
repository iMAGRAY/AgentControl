# SDK commands tailored for this project.
# Update the arrays to align the SDK with the target stack.

_ensure_venv_cmd="[ -d .venv ] || python3 -m venv .venv"
_upgrade_cmd=".venv/bin/pip install --upgrade pip"
_requirements_cmd=".venv/bin/pip install --upgrade -r requirements.txt"

SDK_DEV_COMMANDS=(
  "$_ensure_venv_cmd"
  "$_upgrade_cmd"
  "$_requirements_cmd"
)

SDK_VERIFY_COMMANDS=(
  "$_ensure_venv_cmd"
  "$_upgrade_cmd"
  "$_requirements_cmd"
  ".venv/bin/python -m pytest -q"
)

SDK_FIX_COMMANDS=()
SDK_SHIP_COMMANDS=()

SDK_TEST_COMMAND=".venv/bin/python -m pytest -q"
