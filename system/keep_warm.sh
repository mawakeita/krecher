#!/bin/bash
# Keeps gemma4:e4b loaded on the D12 box during a demo. Stop with Ctrl+C.
# The box's Ollama address is private and not kept in this repo. Set it on the Pi once:
#   echo 'export D12_OLLAMA_URL="http://<box address>/api/generate"' >> ~/.bashrc
# (use the per-user address from the D12 checkout page), then open a new terminal.
URL="${D12_OLLAMA_URL:?Set D12_OLLAMA_URL first (see the comment at the top of this script)}"
while true; do
  if curl -sf -m 30 "$URL" -d '{"model":"gemma4:e4b","keep_alive":"30m"}' > /dev/null; then
    echo "$(date +%H:%M) warm"
  else
    echo "$(date +%H:%M) NO ANSWER: check your lease"
  fi
  sleep 1200
done
