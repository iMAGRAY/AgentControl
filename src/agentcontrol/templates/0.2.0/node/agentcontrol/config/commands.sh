# AgentControl Node.js commands

SDK_DEV_COMMANDS=(
  "npm install"
)

SDK_VERIFY_COMMANDS=(
  "npm install"
  "npm run lint"
  "npm test"
)

SDK_FIX_COMMANDS=(
  "npm run lint -- --fix"
)

SDK_SHIP_COMMANDS=(
  "npm run build"
)

SDK_TEST_COMMAND="npm test"
SDK_COVERAGE_FILE="coverage/lcov.info"
