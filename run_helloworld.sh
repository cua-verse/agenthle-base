#!/bin/bash
# Run the following command in powershell in *REMOTE* machine to launch the server:
# ```powershell
# pip install "cua-computer-server[windows]"
# cua-computer-server --host 0.0.0.0 --port 8000
# ```

# **UNCOMMENT THIS IF YOU ARE ASSIGNED WITH A LITELLM KEY**
# export OPENAI_API_BASE="https://litellm-991596698159.us-west1.run.app"

## Replace with your own API keys and remote machine IP
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export CUA_ENV_API_URL="http://YOUR_REMOTE_MACHINE_IP:8000"


export CUA_TELEMETRY_ENABLED=false
export CUA_PROVIDER="remote"

# Configuration for Remote Windows Environment
export CUA_ENV_TYPE="windows"
export CUA_TELEMETRY_DISABLED="true"
export CUA_ENV_VNC_URL=""
export XDG_DATA_HOME="./trycua"
export EVALUATION_OUTPUT_DIR="./helloworld"


uv run python -m cua_bench.batch.solver ./tasks/helloworld \
    --eval \
    --agent agenthle-agent \
    --model openai/computer-use-preview \
    --max-steps 50 \
    --output-dir $EVALUATION_OUTPUT_DIR



