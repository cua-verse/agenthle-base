#!/bin/bash
# Load environment variables from .env file
if [ -f "$(dirname "$0")/.cua/.env" ]; then
    echo "Loading environment variables from .cua/.env..."
    export $(cat "$(dirname "$0")/.cua/.env" | grep -v '^#' | xargs)
else
    echo "Warning: .cua/.env file not found"
fi

# Configuration for Remote Windows Environment
export CUA_ENV_TYPE="windows"
export CUA_TELEMETRY_DISABLED="true"
export CUA_ENV_VNC_URL=""
export XDG_DATA_HOME="./trycua"
export EVALUATION_OUTPUT_DIR="./trycua/cua-bench/magic_tower_easy"

# Run the Magic Tower Demo task
# Using 'uv run' to ensure we use the correct python environment from the workspace
# uv run cb run task ./tasks/magic_tower \
#     --agent cua-agent \
#     --model openai/computer-use-preview \
#     --provider-type computer \
#     --wait

uv run python -m cua_bench.batch.solver ./tasks/magic_tower_easy \
    --eval \
    --agent agenthle-agent \
    --model openai/computer-use-preview \
    --max-steps 500 \
    --dump \
    --output-dir $EVALUATION_OUTPUT_DIR



