# SDK commands tailored for the Node.js template.

SDK_NODE_ROOT="agentcontrol"

SDK_DEV_COMMANDS=(
  "(cd \"$SDK_NODE_ROOT\" && npm install)"
)

SDK_VERIFY_COMMANDS=(
  "(cd \"$SDK_NODE_ROOT\" && npm install)"
  "(cd \"$SDK_NODE_ROOT\" && npm run lint)"
  "(cd \"$SDK_NODE_ROOT\" && npm test)"
)

SDK_FIX_COMMANDS=(
  "(cd \"$SDK_NODE_ROOT\" && npm run lint -- --fix)"
)

SDK_SHIP_COMMANDS=(
  "(cd \"$SDK_NODE_ROOT\" && npm run build)"
)

SDK_TEST_COMMAND="(cd \"$SDK_NODE_ROOT\" && npm test)"
SDK_COVERAGE_FILE=".agentcontrol/coverage/lcov.info"
